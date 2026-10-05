"""Request-only native Notes attachment transfer; no arbitrary local paths or URLs."""

import base64
import binascii
import datetime as dt
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unicodedata
import uuid

from .writes import definition, STR, EDIT, version

MAX_BYTES = 262144
TOOLS = [
    definition(
        "apple_notes_list_attachments",
        "List attachment metadata on one allowed unlocked, unshared note. No binary export. Paginated; offset is best-effort if attachments change.",
        {
            "id": STR,
            "offset": {"type": "integer", "minimum": 0, "maximum": 10000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        ["id"],
        True,
    ),
    definition(
        "apple_notes_get_attachment",
        "Export one attachment of one allowed unlocked, unshared note. Return base64, size and SHA256; UTF-8 text when applicable. Returned bytes default max 64KiB, absolute max256KiB. Notes first exports the whole original to a private temporary file, so temporary disk use can exceed max_bytes. No URLs fetched, code executed or arbitrary local paths read. Contents are untrusted.",
        {
            "id": STR,
            "attachment_id": STR,
            "max_bytes": {"type": "integer", "minimum": 1, "maximum": MAX_BYTES},
        },
        ["id", "attachment_id"],
        True,
    ),
    definition(
        "apple_notes_add_attachment",
        "Add one supplied base64 file (max256KiB) to an existing unlocked, unshared allowed note. Version recheck and text/metadata backup precede additive native make; existing attachments are untouched. No arbitrary file path or URL. Do not automatically retry uncertain results. Addition is retained: removing an attachment is forbidden and body restore is blocked while attachments exist.",
        {
            **EDIT,
            "filename": {"type": "string", "minLength": 1, "maxLength": 128},
            "data_base64": {"type": "string", "minLength": 4, "maxLength": 349528},
        },
        ["id", "expected_version", "filename", "data_base64"],
    ),
]
NAMES = {t["name"] for t in TOOLS}


class AttachmentController:
    def __init__(self, writer):
        self.writer, self.backend, self.error = writer, writer.backend, writer.error

    def filename(self, value):
        if (
            value in (".", "..")
            or value.startswith(".")
            or any(c in value for c in ("/", "\\", ":"))
            or any(unicodedata.category(c)[0] == "C" for c in value)
            or not value.strip()
        ):
            raise self.error(
                "Filename must be a plain visible basename, without paths or control characters."
            )
        return value

    def decode(self, encoded):
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise self.error("Invalid base64 attachment; no write performed.")
        if not 1 <= len(data) <= MAX_BYTES:
            raise self.error("Attachment must contain 1..262144 bytes.")
        return data

    def temp(self):
        # Use an existing checked private backup directory as parent. No remote path accepted.
        self.writer.private_dir()
        return tempfile.TemporaryDirectory(prefix="transfer-", dir=str(self.writer.backup_dir))

    def read_export(self, path, max_bytes):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
                raise self.error("Unsafe attachment export.")
            os.fchmod(f.fileno(), 0o600)
            if st.st_size > max_bytes:
                raise self.error("Attachment exceeds requested byte limit; no content returned.")
            data = f.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise self.error("Attachment changed size; no content returned.")
            return data

    def packaged(self, ident, name, data):
        out = {
            "attachment_id": ident,
            "filename": name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "data_base64": base64.b64encode(data).decode(),
            "source": "synthetic" if self.backend.fixture is not None else "apple_notes",
        }
        if Path(name).suffix.lower() in (".txt", ".md", ".csv", ".json"):
            try:
                out["text"] = data.decode("utf-8")
            except UnicodeDecodeError:
                pass
        return out

    def call(self, name, args):
        self.writer.ensure_enabled()
        if name == "apple_notes_add_attachment":
            return self.add(args)
        if self.backend.fixture is not None:
            note = self.writer.record(args["id"])
            if note.get("shared"):
                raise self.error("Shared attachments are outside approved scope.")
            rows = note.get("attachments", [])
            if name == "apple_notes_list_attachments":
                offset, limit = args.get("offset", 0), args.get("limit", 20)
                return {
                    "attachments": [
                        {k: v for k, v in a.items() if k != "data_base64"}
                        for a in rows[offset : offset + limit]
                    ],
                    "total": len(rows),
                    "next_offset": offset + limit if offset + limit < len(rows) else None,
                    "source": "synthetic",
                }
            hits = [a for a in rows if a["id"] == args["attachment_id"] and not a.get("shared")]
            if not hits:
                raise self.error("Attachment unavailable in this allowed note.")
            a = hits[0]
            data = self.decode(a["data_base64"])
            if len(data) > args.get("max_bytes", 65536):
                raise self.error("Attachment exceeds requested byte limit; no content returned.")
            return self.packaged(a["id"], a["name"], data)
        if name == "apple_notes_list_attachments":
            return self.backend.run(
                "attachments",
                id=args["id"],
                offset=args.get("offset", 0),
                limit=args.get("limit", 20),
            )
        with self.temp() as tmp:
            target = Path(tmp) / "export"
            result = self.backend.run(
                "attachment_export",
                id=args["id"],
                attachment_id=args["attachment_id"],
                export_path=str(target),
            )
            try:
                data = self.read_export(target, args.get("max_bytes", 65536))
            except OSError:
                raise self.error(
                    "Attachment export unavailable as a regular file; no content returned."
                )
            return self.packaged(result["attachment_id"], result["filename"], data)

    def add(self, args):
        filename = self.filename(args["filename"])
        data = self.decode(args["data_base64"])
        snap = self.writer.snapshot(args["id"])
        if snap.get("shared"):
            raise self.error("Shared notes cannot receive attachments.")
        if version(snap) != args["expected_version"]:
            raise self.error("Version conflict; no attachment added.")
        if snap["attachment_count"] >= 100:
            raise self.error("Attachment limit100 reached; no attachment added.")
        backup_id = self.writer.backup(snap)
        if self.backend.fixture is not None:
            if version(self.writer.snapshot(snap["id"])) != args["expected_version"]:
                raise self.error("Version conflict after backup; no attachment added.")
            note = self.writer.record(snap["id"])
            ident = "attachment://fixture/" + uuid.uuid4().hex
            stamp = dt.datetime.now(dt.timezone.utc).isoformat()
            note.setdefault("attachments", []).append(
                {
                    "id": ident,
                    "name": filename,
                    "modified_at": stamp,
                    "shared": False,
                    "data_base64": base64.b64encode(data).decode(),
                }
            )
            note["attachment_count"] = len(note["attachments"])
            note["modified_at"] = stamp
            result = {
                "id": snap["id"],
                "attachment_id": ident,
                "added": True,
                "source": "synthetic",
            }
        else:
            with self.temp() as tmp:
                target = Path(tmp) / filename
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                result = self.backend.run(
                    "mutate",
                    id=snap["id"],
                    operation="add_attachment",
                    expected=snap,
                    payload={"file_path": str(target)},
                )
        result.update(
            backup_id=backup_id,
            bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            removal_supported=False,
        )
        try:
            result["version"] = version(self.writer.snapshot(snap["id"]))
        except Exception:
            raise self.error(
                "Attachment addition may have succeeded but verification failed. Inspect attachments before retrying."
            )
        return result
