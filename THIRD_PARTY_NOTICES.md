# Third-party notices

OxyBridge's original code and documentation use Apache 2.0. Dependency packages and fonts retain their own licenses; the application license does not replace those terms.

The frontend uses React, React Router, TanStack Query, React Flow, Zustand, Lucide, Manrope, and their dependencies. Full license texts and attribution notices from the pinned frontend production dependency tree are included in [THIRD_PARTY_LICENSES.txt](web/public/THIRD_PARTY_LICENSES.txt). Vite copies this file into the production frontend, where it is available as `/THIRD_PARTY_LICENSES.txt`. Manrope's font license is included there.

Python dependencies are installed from the pinned requirements and lockfile. Their package distributions contain their own license files and notices. Build tooling and development-only packages are installed separately and retain their own licenses.

When updating dependencies, inspect the installed package license files and update the affected notices. Preserve the license files supplied by package managers in redistributed environments. This notice records attribution and does not add restrictions to third-party licenses.
