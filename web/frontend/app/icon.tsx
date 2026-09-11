import { ImageResponse } from 'next/og';

/** Dynamic app icon — matches PWA / navbar “CPU chip” motif (see scripts/gen_pwa_icons.py). */
export const size = { width: 512, height: 512 };
export const contentType = 'image/png';

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(165deg, #0f172a 0%, #312e81 52%, #6366f1 100%)',
        }}
      >
        <div
          style={{
            width: '52%',
            height: '52%',
            borderRadius: 48,
            background: 'linear-gradient(135deg, #c7d2fe 0%, #818cf8 40%, #6366f1 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 0 10px rgba(199,210,254,0.35)',
          }}
        >
          <div
            style={{
              width: '58%',
              height: '58%',
              borderRadius: 28,
              background: '#1e1b4b',
              border: '6px solid #a5b4fc',
            }}
          />
        </div>
      </div>
    ),
    {
      ...size,
    },
  );
}
