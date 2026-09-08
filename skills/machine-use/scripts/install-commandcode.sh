#!/usr/bin/env bash
# install-commandcode.sh <name>
#
# Installs Command Code CLI on a remote machine.
#
#   - Requires state="ready" (base machine working).
#   - Failed provider install does NOT demote machine to broken; sets
#     lastProviderError.commandcode and services.providers.commandcode.installed=false.
#   - Idempotent: re-running re-verifies via smoke test.
#   - Auth is handled by rsyncing ~/.commandcode/ from the laptop after install.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_TAG="machine-use" source "$SCRIPT_DIR/../../_lib/provisioning.sh"

NAME="${1:-}"
if [[ -z "$NAME" ]]; then
  printf '{"ok":false,"stage":"parse-args","message":"usage: install-commandcode.sh <name>"}\n'
  exit 2
fi
if [[ "$NAME" == "local" ]]; then
  printf '{"ok":false,"stage":"precheck","message":"local machine is implicit; install commandcode via npm install -g command-code"}\n'
  exit 1
fi

PROVISIONING_NAME="$NAME"
export PROVISIONING_NAME
ensure_index
machine_exists "$NAME" || { printf '{"ok":false,"stage":"precheck","message":"no such machine: %s"}\n' "$NAME"; exit 1; }

if ! ssh_master_alive "$NAME"; then
  printf '{"ok":false,"stage":"precheck","message":"SSH ControlMaster not alive; run reconnect-ssh.sh first"}\n'
  exit 1
fi

record_provider_failure() {
  local stage="$1" message="$2"
  index_update "$NAME" "$(cat <<JQ
    . + {
      services: ((.services // {}) + {
        providers: ((.services.providers // {}) + {
          commandcode: ((.services.providers.commandcode // {}) + { installed: false })
        })
      })
    }
JQ
  )"
  jq -nc --arg name "$NAME" --arg stage "$stage" --arg msg "$message" \
    '{ok:false,name:$name,stage:$stage,message:$msg,provider:"commandcode"}'
  exit 1
}

emit_progress info "download" "installing Command Code via npm on remote"

mapfile -t SSH_OPTS < <(ssh_base_opts "$NAME")
SSH_TGT="$(ssh_target "$NAME")"

# ── stage: install ───────────────────────────────────────────────────────────

emit_progress info "install" "running npm install -g command-code on remote"
install_log=""
if ! install_log=$(with_timeout 90 "install" -- \
  ssh "${SSH_OPTS[@]}" "$SSH_TGT" "npm install -g command-code 2>&1"); then
  record_provider_failure "install" "npm install -g command-code failed: $(printf %s "$install_log" | tail -3)"
fi

# ── stage: smoke ─────────────────────────────────────────────────────────────

emit_progress info "smoke" "commandcode --version"
version=""
if ! version=$(with_timeout 15 "smoke" -- \
  ssh "${SSH_OPTS[@]}" "$SSH_TGT" "commandcode --version 2>&1"); then
  record_provider_failure "smoke" "commandcode --version failed; check PATH on the remote"
fi
version=$(printf '%s' "$version" | head -1 | tr -d '\r\n')
[[ -z "$version" ]] && record_provider_failure "smoke" "commandcode --version returned empty"

emit_progress info "smoke" "$version"

# ── stage: index-write ───────────────────────────────────────────────────────

ts="$(now_iso)"
version_json="$(printf '%s' "$version" | jq -Rsc .)"
index_update "$NAME" "$(cat <<JQ
  . + {
    services: ((.services // {}) + {
      providers: ((.services.providers // {}) + {
        commandcode: {
          installed: true,
          version: $version_json,
          installedAt: "$ts",
          smokeTestedAt: "$ts"
        }
      })
    })
  }
JQ
)"

jq -nc \
  --arg name "$NAME" \
  --arg version "$version" \
  '{ok:true,name:$name,stage:"done",provider:"commandcode",version:$version}'

emit_progress info "done" "commandcode installed: $version"
