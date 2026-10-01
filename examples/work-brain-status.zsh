# Optional zsh prompt integration for a one-line Work Brain lifecycle banner.
# Source this file from ~/.zshrc after installing Work Brain.

work_brain_status_prompt() {
  local status_line
  status_line="$(work-brain status --quiet 2>/dev/null)"
  [[ -n "$status_line" ]] && print -r -- "$status_line"
}

typeset -ga precmd_functions
precmd_functions+=(work_brain_status_prompt)
