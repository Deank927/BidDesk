# BidDesk Emergent

A local Python/PySide6 desktop prototype for bid intake and review. It uses
SQLite for a separately selected workspace. This source snapshot is based on
**Job Walk Test 4** (2026-11-24). It is not the C# BidDesk and not a release
or an installer.

## Develop in a disposable workspace

1. Use Python 3.11 or newer with the dependencies in `requirements.txt`. A
   fresh virtual environment is recommended.
2. From the repository root, run `python -m pip install -r requirements.txt`.
3. Run `python run_biddesk.py --workspace PATH` after replacing `PATH` with a
   new dedicated development directory outside the checkout whose parent
   exists. Use a blank folder or one previously created by this launcher.
   The launcher does not migrate, clone, or find existing bid workspaces.
4. Run `python -m unittest discover -s tests -v` for the offline tests.

No key is required. Internet connections and the optional Ollama settings
default off/blank in a new workspace. The LA County preview uses the public
OpenBidList over HTTPS when manually enabled; it adds only explicitly
selected records as new leads. The feed date is informational. Verify dates
and instructions against the solicitation and any applicable addenda.

This prototype generates draft materials only. It does not submit bids,
send RSVPs or schedule anything externally. The company placeholder in
drafts must be replaced before real use. Do not commit actual bid files,
workspaces, credentials, or local settings.

## Snapshot and provenance

The core source comes from the 2026-11-24 Job Walk Test 4 test archive
(SHA-256 `f488ff9b585ab5019cd3f04d9df9f1c145ddff1deb08bc45d2b3445de355f728`).
Eleven application modules and the dependency list are byte-for-byte
unchanged. Only the UI branding/profile selection and generated draft company
placeholder were neutralized. The launcher was replaced with an explicit
development-workspace launcher. Demo attachments and data are not included.

No license is added by this snapshot. Confirm authorization before making the
repository public. No native Windows acceptance is implied.
