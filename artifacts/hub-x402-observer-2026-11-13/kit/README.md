# Fixed GET x402 observer rollout

Stage the four reviewed Hub files from `d6a77ce9f` with `python3 kit/stage.py <empty-directory>`. Use `COPYFILE_DISABLE=1 tar --no-xattrs` when transferring the directory from macOS so AppleDouble files stay out of the overlay.

Run `bash deploy.sh prepare` on `factory-vps`. The kit compares the four file preimages against the running container and the Debian-patched image `c62951ec599a`. It builds without network access and checks the resulting source delta, Debian and Python inventory parity, and startup on disposable copies of both SQLite ledgers. The candidate also tests an unpaid fixed GET with pinned terms and rejects an altered recipient, URL and price.

Run `bash deploy.sh switch` after outstanding payout canaries have reached `paid`. The switch pauses the existing timer, waits for an active payout worker, backs up both ledgers, checks Hub and THEMIS, and restores the timer. `bash deploy.sh rollback` restores the previous image using the same coordination. It keeps live SQLite ledgers and completed payouts.
