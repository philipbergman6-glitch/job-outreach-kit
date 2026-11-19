# Third-party notices

## Employer registry (`scripts/data/employers.tsv`)

- **Source:** career-ops employer registry, `employers/boards/`, https://github.com/career-ops-hq/career-ops at commit `58541696402fee52996e04930d790e77f1c84d3d` (2026-11-19).
- **Licensor and database maker:** Santiago Fernández de Valderrama, with the registry's contributors (listed in its `employers/contributions/`).
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/
- **Changes:** reduced to three columns (employer name, board type, board name); kept only the board types `scripts/jobs.py` reads (Join and Pinpoint rows and Personio `.com` rows left out); Workday board names rewritten as `<tenant>.<instance>/<site>` and EU Lever boards as `eu/<slug>`.

The registry credits these lists, from which some of its board addresses were taken (employer names never come from them):

- **ATS Company Directory**, by LastRound AI, CC BY 4.0, https://lastroundai.com/blog/salary-transparency-study-2026
- **ATS Career Page URLs**, by Latmay, CC BY 4.0, https://latmay.com (dataset: https://huggingface.co/datasets/latmay/ats-career-page-urls)
- **ats-scrapers company lists**, https://github.com/kalil0321/ats-scrapers (folder `ats-companies/`, commit `3124192e4edf2f823d4c01a7c21639ff8944533d`), MIT License, Copyright (c) 2026 Kalil Bouzigues.

## Ideas adapted from career-ops code

`scripts/jobs.py` (board readers, the order in which `find` guesses board names) and `scripts/validate.py` (the scope-verb tiers of the fact check) follow designs in career-ops (`providers/`, `discover-ats.mjs`, `verify-cv-facts.mjs`). career-ops code is under the MIT License:

```
MIT License

Copyright (c) 2026 Santiago Fernández de Valderrama

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
