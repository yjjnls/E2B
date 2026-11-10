---
'e2b': minor
'@e2b/python-sdk': minor
'@e2b/cli': minor
---

Add resizable templates: build a template with `maxCpuCount` and pick each sandbox's `cpuCount` on create. `Template.getInfo()` shows a template's CPU counts and throws the new `TemplateNotFoundError` (`TemplateNotFoundException` in Python) for a missing template, and `e2b template list` shows a `Max vCPUs` column.
