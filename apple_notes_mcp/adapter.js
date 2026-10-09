// Fixed scoped JXA adapter; request arrives via stdin, never evaluated as code.
ObjC.import('Foundation');
function run() {
    var input = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
    var req = JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding(input, $.NSUTF8StringEncoding)));
    var notes = Application('com.apple.Notes');
    var folders = [], seen = {};
    function walk(items) {
        for (var i = 0; i < items.length; i++) {
            var folder = items[i], id = folder.id();
            if (seen[id]) continue;
            seen[id] = true;
            folders.push(folder);
            if (folders.length > 500) throw Error('scope-too-large');
            walk(folder.folders());
        }
    }
    try {
        var accounts = notes.accounts();
        for (var i = 0; i < accounts.length; i++) walk(accounts[i].folders());
        if (req.action === 'folders') {
            return JSON.stringify(folders.map(function(f) { return {id: f.id(), name: f.name()}; }));
        }
        if (['metadata', 'get', 'snapshot', 'create', 'mutate', 'attachments', 'attachment_export'].indexOf(req.action) === -1) return JSON.stringify({error: 'Unsupported read operation.'});
        var allowed = folders.filter(function(f) { return req.folder_ids.indexOf(f.id()) !== -1; });
        if (allowed.length !== req.folder_ids.length) return JSON.stringify({error: 'An allowed folder no longer exists; reconfigure scope explicitly.'});
        function attachmentMeta(a) {
            return {id:a.id(), name:a.name().slice(0,512), modified_at:a.modificationDate().toISOString(), shared:a.shared()};
        }
        function attachmentReadMeta(a) {
            var meta = attachmentMeta(a);
            try { meta.content_identifier = a.contentIdentifier(); } catch (e) { meta.content_identifier = null; }
            return meta;
        }
        function snapshot(n, folderID) {
            var body = n.body(), text = n.plaintext();
            var attachments = n.attachments();
            if (attachments.length > 100) throw Error('attachment-snapshot-limit');
            var manifest = attachments.map(attachmentMeta);
            if (body.length > 262144) throw Error('bounded-edit-limit');
            return {id: n.id(), title: n.name(), folder_id: folderID,
                created_at: n.creationDate().toISOString(), modified_at: n.modificationDate().toISOString(),
                locked: n.passwordProtected(), shared: n.shared(),
                attachment_count: attachments.length, attachment_manifest: manifest, body_html: body, text: text};
        }
        if (req.action === 'create') {
            var destinations = allowed.filter(function(f) { return f.id() === req.folder_id; });
            if (destinations.length !== 1 || destinations[0].shared())
                return JSON.stringify({error: 'Destination is unavailable, shared or outside scope.'});
            var made = notes.make({new: 'note', at: destinations[0], withProperties: {name: req.title, body: req.body_html}});
            return JSON.stringify({id: made.id(), source: 'apple_notes', created: true});
        }
        var rows = [], count = 0;
        for (var j = 0; j < allowed.length; j++) {
            var folderID = allowed[j].id();
            var ns = allowed[j].notes();
            count += ns.length;
            if (count > 2000) return JSON.stringify({error: 'Scope exceeds 2000 notes; choose smaller allowed folders.'});
            if (req.action === 'metadata') {
                // Filter locked notes in Notes itself before reading any metadata.
                // Bulk property reads avoid hundreds of per-note Apple Events.
                var readable = allowed[j].notes.whose({passwordProtected: false});
                var ids = readable.id(), titles = readable.name();
                var created = readable.creationDate(), modified = readable.modificationDate();
                var finalIDs = readable.id();
                if (JSON.stringify(ids) !== JSON.stringify(finalIDs) ||
                    titles.length !== ids.length || created.length !== ids.length || modified.length !== ids.length)
                    return JSON.stringify({error: 'Notes changed during metadata read; retry the request.'});
                for (var m = 0; m < ids.length; m++) {
                    rows.push({id: ids[m], title: titles[m].slice(0, 512), folder_id: folderID,
                        created_at: created[m].toISOString(), modified_at: modified[m].toISOString(), locked: false});
                }
                continue;
            }
            // Resolve the requested ID in one bulk read, not one Apple Event per note.
            var targetIndex = allowed[j].notes.id().indexOf(req.id);
            if (targetIndex < 0) continue;
            for (var k = targetIndex; k < Math.min(targetIndex + 1, ns.length); k++) {
                var n = ns[k], id = n.id();
                if (req.action !== 'metadata' && id !== req.id) continue;
                // Check before every metadata/body read; never unlock or show a note.
                if (n.passwordProtected()) continue;
                if (req.action === 'attachments' || req.action === 'attachment_export') {
                    if (n.shared()) return JSON.stringify({error:'Shared notes are outside attachment scope.'});
                    var attachments = n.attachments();
                    if (attachments.length > 10000) return JSON.stringify({error:'Attachment scope too large.'});
                    if (req.action === 'attachments') {
                        var page = attachments.slice(req.offset, req.offset + req.limit).map(attachmentReadMeta);
                        return JSON.stringify({attachments:page, total:attachments.length,
                            next_offset:req.offset + req.limit < attachments.length ? req.offset + req.limit : null, source:'apple_notes'});
                    }
                    var matching = attachments.filter(function(a) { return a.id() === req.attachment_id; });
                    if (matching.length !== 1 || matching[0].shared()) return JSON.stringify({error:'Attachment unavailable in this allowed note.'});
                    var att = matching[0], meta = attachmentMeta(att);
                    try { notes.save(att, {in:Path(req.export_path)}); }
                    catch (e) { return JSON.stringify({error:'Original attachment export unavailable. If it is stored only in iCloud, download it in Notes and retry. No thumbnail was substituted.'}); }
                    return JSON.stringify({attachment_id:meta.id, filename:meta.name, source:'apple_notes'});
                }
                if (req.action === 'snapshot') return JSON.stringify(snapshot(n, folderID));
                if (req.action === 'mutate') {
                    var current = snapshot(n, folderID), expected = req.expected;
                    if (current.shared || current.locked || current.id !== expected.id ||
                        current.folder_id !== expected.folder_id || current.title !== expected.title ||
                        current.modified_at !== expected.modified_at || current.body_html !== expected.body_html ||
                        current.attachment_count !== expected.attachment_count ||
                        JSON.stringify(current.attachment_manifest) !== JSON.stringify(expected.attachment_manifest))
                        return JSON.stringify({error: 'Version conflict or protected note; no change made.'});
                    var op = req.operation, payload = req.payload;
                    if (op === 'add_attachment') {
                        if (current.attachment_count >= 100) return JSON.stringify({error:'Attachment limit reached.'});
                        var added = notes.make({new:'attachment', at:n, withData:Path(payload.file_path)});
                        return JSON.stringify({id:n.id(), attachment_id:added.id(), source:'apple_notes', added:true});
                    } else if (['append', 'edit', 'restore'].indexOf(op) !== -1) {
                        if (current.attachment_count || !payload.body_html || payload.body_html.length > 262144)
                            return JSON.stringify({error: 'Unsafe body replacement blocked.'});
                        n.body = payload.body_html;
                        if (payload.title) n.name = payload.title;
                    } else if (op === 'rename') {
                        if (!payload.title || !payload.title.trim()) return JSON.stringify({error: 'Empty title blocked.'});
                        n.name = payload.title;
                    } else if (op === 'move') {
                        var dest = allowed.filter(function(f) { return f.id() === payload.folder_id; });
                        if (dest.length !== 1 || dest[0].shared()) return JSON.stringify({error: 'Destination outside scope or shared.'});
                        if (folderID !== payload.folder_id) notes.move(n, {to: dest[0]});
                    } else return JSON.stringify({error: 'Unsupported mutation; deletion is unavailable.'});
                    return JSON.stringify({id: n.id(), source: 'apple_notes', changed: true});
                }
                var row = {id: id, title: n.name().slice(0, 512), folder_id: folderID,
                    created_at: n.creationDate().toISOString(), modified_at: n.modificationDate().toISOString(), locked: false};
                if (req.action === 'get') {
                    var text = n.plaintext();
                    row.text = text.slice(0, req.max_chars);
                    row.truncated = text.length > req.max_chars;
                    if (req.format === 'html') {
                        var html = n.body(), items = n.attachments();
                        if (html.length > 33554432 || items.length > 10000) return JSON.stringify({error:'Note HTML/attachment manifest exceeds response bound.'});
                        row.body_html = html;
                        row.representation = 'notes_scripting_html';
                        row.attachments = items.map(attachmentReadMeta);
                    }
                    return JSON.stringify(row);
                }
                rows.push(row);
            }
        }
        if (req.action !== 'metadata') return JSON.stringify({error: 'Note unavailable, locked, or outside allowed folders.'});
        return JSON.stringify(rows);
    } catch (e) {
        return JSON.stringify({error: 'Notes operation did not complete normally. If a write was requested, inspect its target before retrying; its result may be uncertain. No raw diagnostics returned.'});
    }
}
