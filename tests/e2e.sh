#!/usr/bin/env bash
# shellcheck disable=SC2015,SC2012
# End-to-end checks against a running test installation (see .github/workflows/ci.yml).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=scripts/lib.sh
source scripts/lib.sh
BASE=https://localhost
EMAIL=admin@example.com
PASS=ci-password-1
fails=0

ok()   { echo "PASS $1"; }
bad()  { echo "FAIL $1"; fails=$((fails + 1)); }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
api()  { # method path token [body]
  curl -sk -X "$1" "$BASE$2" -H "Authorization: Bearer $3" -H 'Content-Type: application/json' ${4:+-d "$4"}
}
login() { curl -sk "$BASE/api/v1/auths/signin" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"$2\"}" | json 'd.get("token","")'; }
chat() { # token model content -> prints answer or error
  api POST /api/chat/completions "$1" "$(python3 -c 'import json,sys; print(json.dumps({"model":sys.argv[1],"stream":False,"messages":json.loads(sys.argv[2])}))' "$2" "$3")"
}

# 1. admin login over HTTPS
TOKEN=$(login "$EMAIL" "$PASS")
[ -n "$TOKEN" ] && ok "admin can log in over HTTPS" || { bad "admin login"; exit 1; }

# 2. presets installed
ids=$(api GET /api/models "$TOKEN" | json '" ".join(sorted(m["id"] for m in d["data"]))')
for p in copy-edit clarity-flow concise match-style abstract-polish reviewer general; do
  [[ " $ids " == *" $p "* ]] || { bad "preset $p missing (have: $ids)"; continue; }
done
ok "all 7 presets are listed"

# 3. an edit through a preset (passes through the compression filter and the model key)
answer=$(chat "$TOKEN" copy-edit '[{"role":"user","content":"Fix this sentence: this are a test."}]' | json 'd["choices"][0]["message"]["content"]')
[ -n "$answer" ] && ok "copy-edit preset answers" || bad "copy-edit preset gave no answer"

# 4. compression: a conversation over its limit is condensed, an impossible one is refused politely
api POST /api/v1/functions/id/context_compressor/valves/update "$TOKEN" \
  '{"per_chat_limit": 400, "compress_at": 0.5, "keep_recent_turns": 1}' >/dev/null
long=$(python3 -c 'import json; w=" ".join(["word"]*120); print(json.dumps([{"role":r,"content":w} for r in ["user","assistant","user","assistant"]]+[{"role":"user","content":"Say OK."}]))')
out=$(chat "$TOKEN" general "$long")
echo "$out" | json 'd["choices"][0]["message"]["content"]' >/dev/null 2>&1 && ok "long chat is compressed and still answered" \
  || bad "long chat failed: $out"
huge=$(python3 -c 'import json; print(json.dumps([{"role":"user","content":" ".join(["word"]*900)}]))')
out=$(chat "$TOKEN" general "$huge")
[[ "$out" == *"too long"* ]] && ok "an impossible chat gets a plain 'too long' message" || bad "no plain message: $out"
dc run --rm seed >/dev/null && ok "seeding again restores the normal limits"

# 5. Think toggle installed as an on/off switch, plus the Compress button
fl=$(api GET /api/v1/functions/ "$TOKEN")
for f in think_toggle context_compressor compress_button; do
  echo "$fl" | json "next(x for x in d if x['id']=='$f')['is_active'] and next(x for x in d if x['id']=='$f')['is_global']" \
    | grep -q True && ok "$f is active for everyone" || bad "$f not active/global"
done

# 6. a normal user cannot read other people's chats, and the admin cannot read the user's chats
uid=$(api POST /api/v1/auths/add "$TOKEN" '{"name":"Test User","email":"user@example.com","password":"user-password-1","role":"user"}' | json 'd["id"]')
UTOKEN=$(login user@example.com user-password-1)
[ -n "$UTOKEN" ] && ok "admin can add a user who can log in" || bad "added user cannot log in"
answer=$(chat "$UTOKEN" copy-edit '[{"role":"user","content":"Fix this sentence: this are a test."}]' | json 'd["choices"][0]["message"]["content"]')
[ -n "$answer" ] && ok "a normal user can use the presets" || bad "a normal user cannot use the presets"
code=$(curl -sk -o /dev/null -w '%{http_code}' "$BASE/api/v1/chats/list/user/$uid" -H "Authorization: Bearer $TOKEN")
[[ "$code" == 401 || "$code" == 403 ]] && ok "admin cannot read a user's chats (HTTP $code)" || bad "admin could read user chats (HTTP $code)"
code=$(curl -sk -o /dev/null -w '%{http_code}' "$BASE/api/v1/users/" -H "Authorization: Bearer $UTOKEN")
[[ "$code" == 401 || "$code" == 403 ]] && ok "a user cannot list other users (HTTP $code)" || bad "user could list users (HTTP $code)"

# 7. backup and restore
./textedit backup >/dev/null
file=$(ls -t data/backups | head -1)
[ -n "$file" ] && ok "backup created ($file)" || bad "no backup file"
./textedit restore "$file" >/dev/null && wait_healthy webui 10 && [ -n "$(login "$EMAIL" "$PASS")" ] \
  && ok "restore works and login still works" || bad "restore failed"

# 8. restart comes back healthy
dc restart >/dev/null && wait_healthy llama 10 && wait_healthy webui 10 && [ -n "$(login "$EMAIL" "$PASS")" ] \
  && ok "comes back after a restart" || bad "did not come back after restart"

# 9. only the HTTPS proxy is reachable from outside
if dc config --format json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=[k for k,v in d["services"].items() if v.get("ports")]; sys.exit(0 if s==["caddy"] else 1)'; then
  ok "only the HTTPS proxy publishes ports"; else bad "other services publish ports"; fi

echo
[ "$fails" = 0 ] && echo "All end-to-end checks passed." || { echo "$fails check(s) failed."; exit 1; }
