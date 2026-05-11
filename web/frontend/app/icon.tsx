import { ImageResponse } from 'next/og';

/** App icon for manifest / favicon (PNG via ImageResponse). */
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
          background: 'linear-gradient(145deg, #0f172a 0%, #312e81 45%, #6366f1 100%)',
        }}
      >
        <span
          style={{
            fontSize: 280,
            fontWeight: 800,
            color: '#f8fafc',
            letterSpacing: '-0.06em',
            fontFamily:
              'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif',
          }}
        >
          AI
        </span>
      </div>
    ),
    {
      ...size,
    },
  );
}
