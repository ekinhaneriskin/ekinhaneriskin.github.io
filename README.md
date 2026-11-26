# Ekinhan Eriskin — Academic Website | v5.6 — photography and SDG update

This is the consolidated release. No earlier ZIP or patch is needed.

## Install in the existing GitHub repository

1. Back up the existing repository before uploading. Extract this ZIP and copy its contents into the repository root, including the hidden `.github` directory and `.gitignore`. Keep the directory structure.
2. **Keep your existing `background.jpg`, `background2.jpeg`, `foto.jpeg`, `icon.ico`, `CNAME`, and any permitted files in `papers/`.** Original images and the existing custom-domain file were not supplied, so they are not included in this ZIP. Do not delete unrelated existing assets or change DNS settings. The site has a fallback for missing photographs.
3. If the live `publications.json` or `editorial.json` contains more recent data or manual edits than the included snapshot, keep the live version instead of overwriting it. This ZIP includes 29 publication records from the supplied archive and editorial additions, including nine records with existing SDG assignments. No current API snapshot is claimed. The builder supports the old list format and the current object format.
4. GitHub → Settings → Pages → Build and deployment → Source: **GitHub Actions**. Keep the existing custom domain. Replace `.github/workflows/update_pubs.yml`; disable any separate older publication/Pages workflows to avoid competing deployments.
5. Keep existing repository secrets in Settings → Secrets and variables → Actions. Nothing secret is included in the ZIP.
6. Commit the files. In Actions → **Update publications and deploy website** → Run workflow, choose the default branch. The first manual run retrieves publications and SDG suggestions, builds the site and deploys it. Pushes also trigger a static build, without querying the APIs.

## Configuration

| Repository secret | Purpose |
|---|---|
| `SCOPUS_API_KEY` | Existing Scopus publication retrieval and author metrics |
| `OPENALEX_API_KEY` | OpenAlex DOI, abstract and SDG lookup; already configured by the site owner |
| `WOS_API_KEY` | Optional, only after Clarivate approves Starter API access |
| `SCOPUS_INST_TOKEN` | Optional, if applicable to Elsevier institutional authorization |

ORCID, Crossref and Aurora require no additional secret for this implementation. API access and publication/display rights depend on each provider's terms. Do not commit API keys or put them in HTML. Confirm the applicable licences allow the requested retrieval, public storage and display.

`SHOW_SCOPUS_METRICS` is an optional repository **variable**, not a secret. Leave it unset unless the Scopus API licence permits public storage and display of author metrics. Set it to `true` and run the workflow only after verifying permission. Complete API-returned citations, h-index and document count will then appear; absent or incomplete metrics will be hidden. No author-reported fallback is used.

## Operation

- Daily refresh: 02:23 UTC (05:23 Türkiye). GitHub may delay scheduled workflows. The updater discovers newly indexed Scopus publications, updates citations and retrieves missing metadata; it does not remove old records just because an API fails or omits them.
- WoS is optional: when a valid Starter API key is present, it discovers publications using author identifiers and checks existing DOI records. Without the key, ORCID supplies available WoS accession numbers and new publications with a WoS identifier. ORCID cannot guarantee complete coverage or retrieve live WoS citations. WoS and Scopus filters are independent; “only” describes the locally recorded evidence, not proof of exclusion from another index.
- DOI, Scopus identifiers and normalized titles are used to match records. Crossref can fill missing bibliographic fields. The build creates static, searchable HTML with compact, automatically initialized PlumX widgets and clickable DOI links. Live PlumX metrics are supplied by the external service.
- `publications.json` stores the publication archive, independent source citations, SDG assignments and classification provenance. The updater preserves manually added fields. `editorial.json` stores featured research, summaries, video and repository links, and optional approved manuscript permissions. The updater does not edit it. The publication JSON is not deployed as a website download; it is still visible in a public repository.
- SDG logos only: goal names and provenance are provided on hover. OpenAlex supplies DOI-based SDG scores and abstract text where available; Aurora and its Elsevier-based model independently classify title and abstract. Text is sent to those public endpoints but abstracts are not stored by this script. OpenAlex published SDG labels are retained independently, with source attribution. The two Aurora-hosted models can add a goal when both scores are at least 0.80 and an abstract is available. Crossref supplies an abstract fallback where available. Single-model Aurora suggestions are reported for review, not displayed. Scores are model-specific and not calibrated probabilities. Each automatic goal carries its own source. API failures do not erase existing labels.
- Existing `sdg` arrays (including an intentional `[]`) without automatic provenance are protected. For a manual override of an automatically classified paper, set `"sdg": [9, 12]` and `"sdg_manual": true`. To return to automatic classification, remove `sdg`, `sdg_manual`, `sdg_source` and `sdg_classification` from that paper. Successful automated classifications are cached for 90 days, review cases for 30 days and errors for one day. The `force_sdg_refresh` manual workflow input bypasses caching, not manual protection.
- Review the Actions run artifact `sdg-classification-report`. It records the scores, recommendations and errors; it is not deployed or committed. Live Aurora response format and authenticated API access still require verification on the first GitHub run. Unexpected responses are flagged rather than interpreted as SDG assignments.
- For approved author manuscripts only, use the `access` configuration in `editorial.json`: `kind: approved_file`, `approved: true`, `path: papers/filename.pdf`, `version`, `release_on` (ISO date), `license`, and `notice`. Check the specific publisher agreement and required notices first. **Never commit an embargoed or unauthorized PDF to a public repository**, even if the link is hidden. Ordinary publisher access uses DOI links only.

## Design and customization

The site defaults to dark mode, with an optional light mode, rotating original photographs, the research tagline, centered section navigation and an always-visible back-to-top button. Featured research has summaries; the publication list does not. The site displays the institutional email, FIDE profile, academic profile links and research repositories. Copyright starts at 2020 and the end year is dynamic. No personal Gmail address is included in the package.

Make permanent HTML/CSS changes in `tools/index.template.html`, and publication layout changes in `tools/build.py`. `index.html` is generated and may be overwritten by the next build. Update editorial content in `editorial.json`.

## Local preview and checks

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python tools/build.py --stage
python -m http.server 8000 --directory _site
```

Open http://localhost:8000. No API key is needed for tests or preview. The `_site/` folder is generated automatically and is not distributed. Live API credentials, deployment, original photos, and external widget/icon loading are not verified by the local tests.

If a workflow fails, inspect its log. Share only error messages or the SDG report, never credentials. Keep the latest live publication/editorial data when installing future releases.

## v5.6 update of an existing website

Upload the files in the update archive, maintaining paths. Do not replace the live publication/editorial JSON, photos, favicon, CNAME or API settings. The existing workflow builds `index.html` from the updated template on push. Then manually run **Update publications and deploy website**, with `force_sdg_refresh` enabled, and inspect the `sdg-classification-report` artifact. The classifier version change also invalidates v1 caches. The full-height hero restores the original centre/cover photo positioning; your portrait is now in About and uses its native aspect ratio. No actual photograph files are in this archive.


## v5.7 — Automatic GitHub repository discovery

The workflow retrieves owned public repositories from the GitHub REST API on every scheduled, manual and push build. No additional API key is needed. It excludes forks, `ekinhaneriskin.github.io` and the account's profile README repository `ekinhaneriskin`. Archived public repositories are retained and labelled Archived. New entries use GitHub's description and language; existing curated titles and descriptions in `editorial.json` take precedence. Successful snapshots are committed to `repositories.json`; the generated HTML is the only repository listing deployed to the website. API failures preserve the last successful snapshot; before the first successful sync, the site uses the existing curated list with exclusions. If a repository becomes private or is deleted, it disappears after the next successful sync.

To hide more repositories, add a top-level array to your existing `editorial.json`, e.g. `"exclude_repositories": ["example-repo"]`. Do not replace your existing editorial or publication data. The list is not a licence check; review public repositories for material appropriate for your academic site.
