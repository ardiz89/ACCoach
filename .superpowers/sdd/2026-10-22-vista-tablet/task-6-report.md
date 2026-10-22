# Task 6 report

## Implementation
- netinfo.device_urls: added "tablet" key. livepanel_ui: QR and address use urls["tablet"].
- engineer.html: ES3 inline script in <head> (before every <script src>): try { new Function("async function f(){}") } catch (e) { location.replace("/tablet") }. Language injection in api.py only touches the i18n.js script tag, unaffected.
- Existing tests updated: test_netinfo (dict), test_livepanel_ui (fixture + two address asserts now /tablet).
- Guide: new section "La vista tablet" / "The tablet view" (before "Aprire il report sul telefono o sul tablet"), plus one sentence in the "Collega il tablet" step pointing to it. Claims checked against tablet.html/tablet.js/i18n.js (button labels, 8 s strip, "Full page" link, at_box/BOX-change modes, restore button, new file not overwriting).

## RED / GREEN
- RED: tests/test_tablet_wiring.py 5 failed (KeyError 'tablet', urls["tablet"] absent, no redirect script).
- GREEN: wiring + netinfo + livepanel_ui 57 passed. Extra test added: redirect fires when `async` is rejected (node, Function patched), proving the script is not inert.
- Full suite: 3077 passed. First run failed one tone test (guide_en, "long" sentence); shortened.

## Guide paragraphs (IT)
See GUIDA.md "### La vista tablet" (bullets: In pista, Avviso di rientro, Fermo ai box, Una modifica respinta; closing paragraph on /engineer and the automatic redirect). EN mirror in docs/FAQ.md "### The tablet view".

## Self-review / concerns
- The starting-file rule (last HONE-written since web process start, else most recently modified) is stated from the brief, not re-verified in the backend code.
- The redirect cannot be tried on a real Safari 9; only node-simulated.
- No Norton/firewall mention, as requested.
