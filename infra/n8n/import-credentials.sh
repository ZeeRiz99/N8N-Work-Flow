#!/bin/sh
# Runs inside the n8n container. Reads credential JSON from stdin, imports it, and removes
# every temporary file. n8n's own output is never printed, because it can echo the input.
umask 077
tmp=/tmp/rl-creds.json
log=/tmp/rl-creds.log
# Windows PowerShell 5.1 prefixes piped text with a UTF-8 BOM; strip it before n8n parses the JSON.
node -e "let d='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>d+=c).on('end',()=>require('fs').writeFileSync('$tmp',d.replace(/^﻿/,''),{mode:0o600}))"
n8n import:credentials --input="$tmp" > "$log" 2>&1
code=$?
rm -f "$tmp"
if [ "$code" -eq 0 ]; then
  count=$(grep -o 'Successfully imported [0-9]*' "$log" | grep -o '[0-9]*$')
  echo "n8n: imported ${count:-?} credential(s)"
else
  echo "n8n: import failed (output hidden)"
fi
rm -f "$log"
exit "$code"
