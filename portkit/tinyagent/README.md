# TinyAgent

This folder contains an attempt at a builtin & more controllable agent.  It
works reasonably well for simple symbols, but I've found it struggles (at least
with Gemini Pro) when trying to handle more complex problems.

The weakness is a result of:

* tooling issues (the LLM doesn't like to call a tool to perform a patch, and runs into formatting errors frequently)
* insufficient tools (we should really give the LLM access to bash directly)
* weak prompting (the editing prompt can likely be optimized to make the model much better at Rust etc)