# Public framework releases

Keep the public dependency-free Python/vanilla-JavaScript runtime compatible with Python 3.11+. All chat UI/runtime changes must be included in the explicit standalone export allowlist. Never include local history, user files, credentials or private app configuration in commits. Preserve the version/build footer; bump gptapps/version.py VERSION for a release, retain fresh standalone build stamps, and verify both Studio and exported app behavior before pushing. Run the full unittest suite and the dependency-free Node tests documented in README.md.
