# Your own document templates

Put Jinja2 Markdown templates here (`*.md.j2`) to change what MAYA generates on a model's
**Documents** tab.

- A file named like a built-in **replaces** it: `model_card.md.j2`, `validation_report.md.j2`,
  `model_documentation.md.j2`. Copy the built-in from `maya/documents/templates/` and edit it.
- Any other `*.md.j2` file becomes a template of its own. Its first line says what it is:

      {# maya: kind=model_card; title=Model card (firm layout) #}

- In a template, `facts` is the model's record, `ai("key", "instruction")` asks a language
  model to draft a section from those facts (labelled as drafted until the document is
  approved), and `table(rows, ["col", ...])` makes a table.

The full reference is in MAYA's Help → guides → *What each designer expects* →
*Documents and model cards*. This folder is `documents.template_dir` in
`config/application.yaml`.
