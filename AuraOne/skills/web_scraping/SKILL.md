---
name: web-scraping
description: Use Firecrawl to extract markdown content from websites.
---

# Web Scraping Skill

Use this skill when the user wants to read, scrape, or analyze the content of a web page URL.

## Workflow:
1. Identify the URL in the user's request.
2. Call the `scrape_web` tool with the identified URL.
3. Once the markdown content is returned:
   - Extract the relevant information requested by the user.
   - Summarize, translate, or rewrite the content as specified.
