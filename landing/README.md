# Rekolekt landing page

The standalone product page is served at https://rekolekt.subcult.tv. It uses the
selected SUBCULT Studio Rekolekt pack. Asset origins and hashes are recorded in
`../docs/rekolekt-brand-provenance.json`; fonts include their redistribution licenses.
The supplied marks are copied without geometry changes.

The interactive transcript uses a short public automated-transcript excerpt from
HasanAra. `source-example.json` records the source URLs, retrieval date and exact
segments. Selection updates a timestamped source link and a copyable range link. The product page makes no claim of a hosted Rekolekt signup service.
The shared application uses the selected palette and local fonts by default;
existing runtime client profiles continue to override that theme. The optional
`config/branding/rekolekt.json` profile supplies the product identity to a deployment.

## Local preview and checks

From the repository root:

```sh
rtk proxy python3 -m http.server 4187 --bind 127.0.0.1 --directory landing
rtk proxy node --check landing/demo.js
rtk proxy docker build -t rekolekt-landing:review landing
```

## Social preview

`social-preview.svg` is the source for `social-preview.png` (1200 × 630). Its text
repeats the page headline, so edit both together. The SVG names only generic
`sans-serif` and `monospace` families; the committed PNG was rendered on Kvant,
where they resolve to Liberation Sans and BitstromWera Nerd Font
(rsvg-convert 2.62.3). Another font setup gives different glyphs, so look at the
PNG after rendering.

```sh
rtk proxy rsvg-convert -w 1200 -h 630 landing/social-preview.svg -o landing/social-preview.png
rtk proxy sha256sum landing/social-preview.png landing/style.css landing/demo.js
```

`index.html` versions `style.css`, `demo.js` and the `og:image` URL with `?v=` and
the first 12 hex characters of the file's SHA-256. Update the matching value
whenever one of those files changes.

Check the rendered desktop and narrow layouts, search matches and empty results,
passage selection, keyboard access, FAQ disclosure, local fonts and images.

## Deployment

Build the `landing/` Docker context with a revision-specific image tag. Set
`REKOLEKT_LANDING_IMAGE` in the deployment directory and run `docker compose -f
compose.yml up -d`. The service joins the existing `projects` network. Import
`edge.Caddyfile` into the Almaz edge Caddy configuration, validate it, and reload.
The existing wildcard Cloudflare tunnel routes the hostname to Caddy.

Back up the edge Caddyfile before adding the import. Roll back an existing release
by setting the prior qualified image and recreating only `rekolekt-landing`. For
the initial release, remove only the Rekolekt import, validate/reload Caddy, then
stop this Compose project. Keep the release directory and recovery files.

This deployment is separate from the HasanAra application, database and workers.
