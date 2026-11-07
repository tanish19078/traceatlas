# TraceAtlas JBOX deployment

JBOX builds and publishes projects through its authenticated browser workspace.
It does not currently import this static renderer or expose a deployment CLI.

## Create the project

1. Sign in at <https://jboxai.com/> and create a new project named
   **TraceAtlas Evidence Explorer**.
2. Upload these reference screenshots from this machine:
   - `C:\Users\Tanish Singla\AppData\Local\Temp\opencode\traceatlas-navy-desktop.png`
   - `C:\Users\Tanish Singla\AppData\Local\Temp\opencode\traceatlas-navy-mobile.png`
3. Paste the prompt below.
4. Review the generated flow before building. It should contain one public
   directory screen, a company-detail interaction, and a comparison dialog.

## JBOX build prompt

```text
Build a polished, public, single-page company evidence explorer named TraceAtlas.
Use Next.js, TypeScript, Tailwind and accessible native interactions. Do not add
authentication, a database, an admin dashboard, pricing, testimonials, or generic
SaaS sections. Match the attached desktop and mobile screenshots closely.

Visual direction:
- Midnight navy foundation: #071C2D, #0A2941 and #123C59.
- Coral primary accent: #FF6B5E, with #DD4F45 for hover and #FFE8E3 for soft states.
- White cards on a cool #F3F6F8 canvas with a subtle 42px grid.
- Large editorial hero reading “Research you can check.” with “check.” in coral.
- Compact monospace eyebrows, rounded evidence cards, restrained shadows, and
  coral focus rings. The result should feel like investigative intelligence,
  not a generic template.

Page behavior:
- Header brand “TraceAtlas”, anchor links to Explore companies and How it works,
  and a visible “Sample gallery” pill.
- Hero with the evidence-first message, CTA, counts for 3 profiles, 21 supported
  facts and 3 source records, plus a glass “Every fact has a trail” card.
- Clearly label all records as demonstration/synthetic data.
- Search instantly by company name, organisation number, place or activity.
- Render three company cards:
  1. SYNTHETIC — Northlight Materials AS, 900000006, Bergen, 12 employees.
  2. SYNTHETIC — Fjord Workshop AS, 900000014, Trondheim, 5 employees.
  3. SYNTHETIC — Brightpath Logistics AS, 900000022, Tromsø, 34 employees.
- Each card shows status, summary, supported-fact/evidence counts, a Compare
  toggle and an “Open company profile” disclosure.
- The open profile lists facts with an expandable Evidence control. Evidence
  shows “Synthetic fixture”, retrieval timestamp, JSON pointer and SHA-256 hash.
  Synthetic records must never link to a real registry page.
- Users can select exactly two companies. Enable a coral Compare button only
  when two are selected. Open an accessible modal with a side-by-side table of
  organisation number, status, summary and all facts with provenance.
- Include visible research gaps and an empty-search result state.
- Support keyboard search with “/” and Ctrl/Cmd+K, Escape/modal close, clear focus
  styles, reduced motion and semantic labels.
- At 820px use one card column. At 390px there must be no horizontal page
  overflow; comparison may scroll inside its modal.

Keep the sample data in a typed local data module so the app works without APIs.
Every visible claim must retain its evidence metadata. Do not invent additional
companies, customer logos, statistics or source links.
```

## Publish

1. Test search, opening a profile, selecting two companies, comparison, evidence
   expansion, keyboard focus, and the 390px mobile preview.
2. Open the project publishing/integration panel and choose **Hosting**.
3. Choose an address such as `traceatlas` and publish.
4. Copy the final `https://<address>.sites.jboxai.com/` URL. Do not submit a
   temporary `preview.jboxai.com` URL.
5. Capture the JBOX Hosting panel showing the live address as proof for the bonus.

After publishing, provide the URL so it can be checked for HTTP availability,
mobile overflow, search, comparison, evidence details and metadata.
