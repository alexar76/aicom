// The worker has no network API. Only the host's fixed broker command starts a job.
const timer = setInterval(() => {}, 60_000);
for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => { clearInterval(timer); process.exit(0); });
