/* AICOM learn hub — mesh backdrop + track filters ( /learn/ only ).
 * Hub-and-spoke topology — never a regular hexagon / hexagram. */
(() => {
  const canvas = document.getElementById("learn-galaxy");
  if (canvas) {
    const ctx = canvas.getContext("2d");
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const host = canvas.parentElement || document.body;
    let W = 0, H = 0, dpr = 1, t0 = performance.now();
    const mouse = { x: 0.5, y: 0.45, tx: 0.5, ty: 0.45 };
    const stars = [];
    // Irregular mesh: center Hub + satellites on uneven radii/angles (not 6-fold).
    const nodes = [
      { kind: "hub", x: 0, y: 0, c: "#38e0ff", r: 5 },
      { kind: "sat", a: 0.15, rr: 0.34, c: "#38ffa6", r: 3.2 },
      { kind: "sat", a: 1.05, rr: 0.42, c: "#ffcc4d", r: 2.8 },
      { kind: "sat", a: 1.85, rr: 0.28, c: "#a78bfa", r: 3.0 },
      { kind: "sat", a: 2.7, rr: 0.46, c: "#ff5a36", r: 2.6 },
      { kind: "sat", a: 3.55, rr: 0.33, c: "#7ee7ff", r: 3.1 },
      { kind: "sat", a: 4.4, rr: 0.4, c: "#9fe9ff", r: 2.7 },
      { kind: "sat", a: 5.35, rr: 0.26, c: "#38e0ff", r: 2.9 },
    ];
    // Edges: hub→all + a few peer hops (asymmetric, not star-of-David).
    const edges = [
      [0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [0, 6], [0, 7],
      [1, 2], [2, 4], [3, 5], [5, 6], [6, 1], [4, 7],
    ];

    function resize() {
      dpr = Math.min(devicePixelRatio || 1, 2);
      const rect = host.getBoundingClientRect();
      const w = Math.max(320, rect.width || innerWidth);
      const h = Math.max(280, rect.height || Math.min(innerHeight * 0.55, 520));
      W = canvas.width = Math.floor(w * dpr);
      H = canvas.height = Math.floor(h * dpr);
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
      stars.length = 0;
      const n = Math.min(160, Math.floor((W * H) / (18000 * dpr)));
      for (let i = 0; i < n; i++) {
        stars.push({
          x: Math.random(),
          y: Math.random(),
          z: Math.random() * 0.9 + 0.1,
          s: Math.random() * 1.2 + 0.25,
          c: ["#38e0ff", "#9fe9ff", "#ffffff", "#38ffa6"][(Math.random() * 4) | 0],
        });
      }
    }
    resize();
    addEventListener("resize", resize, { passive: true });
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(resize).observe(host);
    }
    addEventListener("pointermove", (e) => {
      const rect = host.getBoundingClientRect();
      if (!rect.width) return;
      mouse.tx = (e.clientX - rect.left) / rect.width;
      mouse.ty = (e.clientY - rect.top) / rect.height;
    }, { passive: true });

    function frame(now) {
      mouse.x += (mouse.tx - mouse.x) * 0.06;
      mouse.y += (mouse.ty - mouse.y) * 0.06;
      const u = ((now - t0) % 28000) / 28000;
      ctx.clearRect(0, 0, W, H);

      const cx = W * (0.5 + (mouse.x - 0.5) * 0.03);
      const cy = H * (0.48 + (mouse.y - 0.5) * 0.03);
      const scale = Math.min(W, H);

      // soft nebula blobs (no geometric figure)
      [
        [0.22, 0.3, 0.4, "rgba(56,224,255,0.09)"],
        [0.78, 0.35, 0.32, "rgba(56,255,166,0.06)"],
        [0.55, 0.7, 0.3, "rgba(56,120,200,0.05)"],
      ].forEach(([x, y, r, col]) => {
        const g = ctx.createRadialGradient(x * W, y * H, 0, x * W, y * H, r * W);
        g.addColorStop(0, col);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
      });

      stars.forEach((s, i) => {
        const tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(u * Math.PI * 4 + i));
        const px = s.x * W + (mouse.x - 0.5) * 12 * s.z * dpr;
        const py = ((s.y + u * 0.03 * s.z) % 1) * H;
        ctx.globalAlpha = tw * (0.2 + s.z * 0.45);
        ctx.fillStyle = s.c;
        ctx.beginPath();
        ctx.arc(px, py, s.s * dpr * s.z, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1;

      // faint orbital rings (ellipses — not a polygon star)
      ctx.strokeStyle = "rgba(56,224,255,0.07)";
      ctx.lineWidth = 1 * dpr;
      [0.22, 0.34, 0.46].forEach((rr, i) => {
        ctx.beginPath();
        ctx.ellipse(cx, cy, rr * scale, rr * scale * 0.55, 0.12 * i, 0, Math.PI * 2);
        ctx.stroke();
      });

      const pos = nodes.map((n) => {
        if (n.kind === "hub") return { x: cx, y: cy, n };
        const a = n.a + u * Math.PI * 2 * 0.08;
        const wobble = 1 + 0.04 * Math.sin(u * Math.PI * 2 + n.a * 3);
        return {
          x: cx + Math.cos(a) * n.rr * scale * wobble,
          y: cy + Math.sin(a) * n.rr * scale * 0.58 * wobble,
          n,
        };
      });

      ctx.lineWidth = 1.1 * dpr;
      edges.forEach(([i, j], ei) => {
        const a = pos[i], b = pos[j];
        ctx.strokeStyle = ei < 7
          ? "rgba(56,224,255,0.22)"
          : "rgba(56,255,166,0.12)";
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      });

      pos.forEach((p, i) => {
        const pulse = 0.6 + 0.4 * Math.sin(u * Math.PI * 2 + i * 0.7);
        const glowR = (p.n.kind === "hub" ? 28 : 14) * dpr * pulse;
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowR);
        g.addColorStop(0, p.n.c);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(p.x, p.y, glowR, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#fff";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.n.r * dpr, 0, Math.PI * 2);
        ctx.fill();
      });

      // packet hop along hub→satellite edges only
      const hopEdges = edges.slice(0, 7);
      const hop = (u * hopEdges.length) % hopEdges.length;
      const ei = Math.floor(hop);
      const sf = hop - ei;
      const [ia, ib] = hopEdges[ei];
      const ax = pos[ia].x + (pos[ib].x - pos[ia].x) * sf;
      const ay = pos[ia].y + (pos[ib].y - pos[ia].y) * sf;
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(ax, ay, 3.2 * dpr, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.3)";
      ctx.beginPath();
      ctx.arc(ax, ay, 8 * dpr, 0, Math.PI * 2);
      ctx.stroke();

      if (!reduce) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  const btns = document.querySelectorAll(".learn-filter [data-filter]");
  const tracks = document.querySelectorAll("[data-track]");
  if (btns.length && tracks.length) {
    btns.forEach((btn) => {
      btn.addEventListener("click", () => {
        btns.forEach((b) => b.classList.toggle("active", b === btn));
        const f = btn.getAttribute("data-filter");
        tracks.forEach((el) => {
          el.hidden = f !== "all" && el.getAttribute("data-track") !== f;
        });
      });
    });
  }

  // Soft stagger only — cards are always visible (no opacity:0; Firefox-safe).
  document.querySelectorAll(".learn-card").forEach((c, i) => {
    c.style.setProperty("--i", String(i % 8));
    c.classList.add("in");
  });
})();
