#!/usr/bin/env bash
# Scan git changes for likely API keys / secrets. Called from Husky pre-commit / pre-push.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

mode="${1:-staged}" # staged | push

mapfile -t files < <(
  if [[ "$mode" == "staged" ]]; then
    git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true
  elif [[ ! -t 0 ]]; then
    commits=()
    while read -r local_ref local_sha remote_ref remote_sha; do
      [[ -z "${local_sha:-}" || "$local_sha" == "0000000000000000000000000000000000000000" ]] && continue
      if [[ -z "${remote_sha:-}" || "$remote_sha" == "0000000000000000000000000000000000000000" ]]; then
        while IFS= read -r c; do commits+=("$c"); done < <(
          git rev-list "$local_sha" --not --remotes 2>/dev/null || git rev-list "$local_sha"
        )
      else
        while IFS= read -r c; do commits+=("$c"); done < <(
          git rev-list "$local_sha" "^$remote_sha" 2>/dev/null || true
        )
      fi
    done
    if ((${#commits[@]})); then
      git diff-tree --no-commit-id --name-only -r "${commits[@]}" | sort -u
    fi
  else
    git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true
  fi
)

if ((${#files[@]} == 0)); then
  exit 0
fi

fail=0
report() {
  echo "error: possible secret in $1" >&2
  echo "  $2" >&2
  fail=1
}

is_placeholder() {
  local v="$1"
  [[ -z "$v" ]] && return 0
  [[ "$v" == *"..."* ]] && return 0
  [[ "$v" =~ ^(changeme|change-me|your[_-]?key|xxx+|placeholder|dummy|example|test)$ ]] && return 0
  return 1
}

check_content() {
  local file="$1"
  local content="$2"
  local line num=0 key val

  while IFS= read -r line || [[ -n "$line" ]]; do
    num=$((num + 1))
    if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"
      val="${val#\"}"; val="${val%\"}"
      val="${val#\'}"; val="${val%\'}"
      if [[ "$key" =~ (KEY|TOKEN|SECRET|PASSWORD) ]] && ! is_placeholder "$val"; then
        if [[ "$val" =~ ^sk-proj-[A-Za-z0-9_-]{20,} ]] || \
           [[ "$val" =~ ^sk-[A-Za-z0-9_-]{20,} ]] || \
           [[ "$val" =~ ^fc-[0-9a-f]{20,} ]] || \
           [[ "$val" =~ ^ghp_[A-Za-z0-9]{20,} ]] || \
           [[ "$val" =~ ^github_pat_[A-Za-z0-9_]{20,} ]] || \
           [[ "$val" =~ ^AKIA[0-9A-Z]{16} ]]; then
          report "$file" "line $num: $key looks like a real credential"
        fi
      fi
    fi
    if [[ "$line" =~ sk-proj-[A-Za-z0-9_-]{20,} ]]; then
      report "$file" "line $num: OpenAI project API key pattern"
    elif [[ "$line" =~ (^|[^A-Za-z0-9_-])sk-[A-Za-z0-9_-]{24,} ]]; then
      report "$file" "line $num: OpenAI API key pattern"
    elif [[ "$line" =~ fc-[0-9a-f]{24,} ]]; then
      report "$file" "line $num: Firecrawl API key pattern"
    elif [[ "$line" =~ ghp_[A-Za-z0-9]{36} ]]; then
      report "$file" "line $num: GitHub personal access token"
    elif [[ "$line" =~ AKIA[0-9A-Z]{16} ]]; then
      report "$file" "line $num: AWS access key id"
    fi
  done <<< "$content"
}

for f in "${files[@]}"; do
  [[ -z "$f" ]] && continue
  if [[ "$f" =~ ^\.env(\.|$) ]]; then
    report "$f" "env files must not be committed (use .gitignore)"
    continue
  fi
  case "$f" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.pdf|*.zip|*.gz|*.pyc|*.so|*.dylib|*.bin|*.exe|*.dll)
      continue
      ;;
  esac

  if [[ "$mode" == "staged" ]]; then
    if git show ":$f" &>/dev/null; then
      content=$(git show ":$f" 2>/dev/null || true)
    elif [[ -f "$f" ]]; then
      content=$(cat "$f" 2>/dev/null || true)
    else
      continue
    fi
  else
    content=$(git show "HEAD:$f" 2>/dev/null || true)
    [[ -z "${content:-}" ]] && continue
  fi

  check_content "$f" "$content"
done

if ((fail)); then
  echo >&2
  echo "Hook blocked this operation. Remove secrets, rotate exposed keys, keep credentials in .env only." >&2
  exit 1
fi

exit 0
