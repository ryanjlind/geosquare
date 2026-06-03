# Copilot Instructions

- Never make assumptions about requested changes.
- If requirements are incomplete or unclear, confirm them with the user before modifying any files.
- Do not change files until the user explicitly approves the exact implementation details.
 - Never add code that suppresses, hides, or silences errors (for example, returning HTTP 204 to hide repeated 404s) unless the user explicitly requests that behavior.
 - Always obtain explicit approval from the user before applying any fix, even if it appears low-risk.
- Give only the necessary information. Do not repeat yourself, editorialize, summarize, or add intros/outros.
- If you see something say something, don't gloss over or repeat patterns that are bad. Raise the issue or potential issue to me.
- Under no circumstances should you use contrasting language. Do not ever frame an explanation of what something is by contrasting it against something that it isn't.

# Architecure

- Routes -> Core -> Helpers
- No SQL in Routes.
- No inline styles.
- Helpers should be light-weight and re-usable across many core files.

# Code Style
- Never implement silent defaults, fallbacks, or "safety guards"
- For exmaple, "if (!user) return null" is not acceptable. Instead, throw an error or return a specific message.
- Ask the user how to handle any errors. Do not make asumptions about error handling.
- Always ask the user for specific error handling instructions, such as whether to throw an error, return a specific message, or log the error. Do not make assumptions about error handling.  
