# Bundled browser dependencies

These files are distributed with the framework and generated apps. They are served
locally, so Markdown rendering does not load code from a CDN.

| Package | Version | Source | License file |
| --- | --- | --- | --- |
| Marked | 18.1.3 | https://registry.npmjs.org/marked/-/marked-18.1.3.tgz | marked-LICENSE.txt (MIT) |
| DOMPurify | 3.4.17 | https://registry.npmjs.org/dompurify/-/dompurify-3.4.17.tgz | dompurify-LICENSE.txt (Apache-2.0 OR MPL-2.0) |

Downloaded package archives were verified against the npm registry integrity values:

```text
marked: sha512-9ChMH8EVVgjgID49nsL6IWxWk5c6GtAsq/xw7U1ggkjkU5AGuv68oLTVlFRtvcUYZtpbNyjyvGo3YDu0fGapiw==
dompurify: sha512-B/pSlYVHQ58kqISD/yDjuJ1yfzI34m1gF4lAod2bwSRhiN4K5Cl3H8Af7hqB2PmTL911tdEudnnXn5FnhRoz0w==
```

Upstream projects: https://github.com/markedjs/marked and
https://github.com/cure53/DOMPurify. Keep these libraries and their licenses together
when updating or redistributing the runtime.
