# langfuse/langfuse:2 (split Docker image)

The Docker image `langfuse/langfuse:2` was exported, gzipped, and split into
<100MB parts so it can be stored on GitHub (single-file limit is 100MB).

Files:
- `langfuse-2.tar.gz.part-aa`, `...part-ab`, `...part-ac` — the split archive
- `parts.sha256` — checksums of each part

## Restore the image

**Linux / macOS / Git Bash:**

```bash
cat langfuse-2.tar.gz.part-* > langfuse-2.tar.gz
docker load < langfuse-2.tar.gz
```

**Windows PowerShell:**

```powershell
cmd /c "copy /b langfuse-2.tar.gz.part-aa+langfuse-2.tar.gz.part-ab+langfuse-2.tar.gz.part-ac langfuse-2.tar.gz"
docker load -i langfuse-2.tar.gz
```

## (Optional) verify parts before restoring

```bash
sha256sum -c parts.sha256
```

## How the parts were created

```bash
docker save langfuse/langfuse:2 | gzip > langfuse-2.tar.gz
split -b 90m langfuse-2.tar.gz langfuse-2.tar.gz.part-
```
