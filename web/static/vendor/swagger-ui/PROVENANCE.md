# Swagger UI, vendored

`swagger-ui-bundle.js` and `swagger-ui.css`, taken from the `swagger-ui-py`
25.7.1 wheel (`swagger_ui/static/`), which packages the upstream Swagger UI
distribution.

**Why they are here rather than on a CDN.** FastAPI's `/docs` loads both from
`cdn.jsdelivr.net`. This platform's Content-Security-Policy is `script-src
'self'` — deliberately, because every other asset in the interface is vendored
so it renders air-gapped — so the default `/docs` was a blank page on any
instance with the headers on, which is every instance. A CDN exception would
have been a hole in the policy opened for a documentation page, on a platform
whose own argument is that nothing here calls out.

Two files only: the editor bundles, the ES module variants and the standalone
preset in that wheel are not used and are not carried.
