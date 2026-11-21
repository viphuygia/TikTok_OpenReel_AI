import React, { useEffect, useRef } from 'react';
import { continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

const sharedLottieCache = new Map<string, any>();
let sharedLottiePromise: Promise<any> | null = null;

function loadSharedLottieLib(): Promise<any> {
  if (typeof window === 'undefined') return Promise.resolve(null);
  if ((window as any).lottie) return Promise.resolve((window as any).lottie);
  if (!sharedLottiePromise) {
    sharedLottiePromise = new Promise((resolve) => {
      const sc = document.createElement('script');
      sc.src = staticFile('assets/lottie.min.js');
      sc.async = true;
      sc.onload = () => resolve((window as any).lottie || null);
      sc.onerror = () => resolve(null);
      document.head.appendChild(sc);
    });
  }
  return sharedLottiePromise;
}

export function resolveLottieStem(emoji?: string, label?: string): string {
  const txt = `${emoji || ''} ${label || ''}`.toLowerCase();
  if (/🔥|lửa|nướng|bếp|cháy|hot|deal/.test(txt)) return '1f525';
  if (/🌈|cầu vồng|biển|đảo|mùa hè/.test(txt)) return '1f308';
  if (/☀️|🌞|nắng|sáng|bình minh|hoàng hôn|🌅/.test(txt)) return '1f31e';
  if (/🌙|đêm|khuya|ngủ|sao đêm/.test(txt)) return '1f31b';
  if (/🌸|hoa|cảnh|vườn|đẹp/.test(txt)) return '1f338';
  if (/🍀|🌿|🍃|rừng|cây|cỏ|thiên nhiên|trại|🏕/.test(txt)) return '1f340';
  if (/🎉|🎊|chúc mừng|vui|lễ|tiệc/.test(txt)) return '1f389';
  if (/🚀|đi|xe|đường|hành trình|du lịch|🚗|✈/.test(txt)) return '1f680';
  if (/❤️|💖|tim|yêu|thích|chill|☕/.test(txt)) return '2764_fe0f';
  if (/⚡|năng lượng|nhanh|sốc/.test(txt)) return '26a1';
  if (/✅|chuẩn|ok|xong/.test(txt)) return '2705';
  if (/👍|hay|tốt/.test(txt)) return '1f44d';
  if (/💡|mẹo|ý tưởng/.test(txt)) return '1f4a1';
  if (/🌟|⭐|kỷ niệm|đỉnh/.test(txt)) return '1f31f';
  return '2728';
}

export const SharedLottieSticker: React.FC<{
  stem: string;
  size: number;
  startFrame?: number;
}> = ({ stem, size, startFrame = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const boxRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<any>(null);

  useEffect(() => {
    let cancelled = false;
    const handle = delayRender(`SharedLottie:${stem}`);
    (async () => {
      try {
        const lottieLib = await loadSharedLottieLib();
        if (!lottieLib) throw new Error('lottie.min.js unavailable');
        let animData = sharedLottieCache.get(stem);
        if (!animData) {
          const resp = await fetch(staticFile(`assets/lottie_stickers/${stem}.json`));
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          animData = await resp.json();
          sharedLottieCache.set(stem, animData);
        }
        if (cancelled || !boxRef.current) return;
        boxRef.current.innerHTML = '';
        const anim = lottieLib.loadAnimation({
          container: boxRef.current,
          renderer: 'svg',
          loop: true,
          autoplay: false,
          animationData: JSON.parse(JSON.stringify(animData)),
        });
        animRef.current = anim;
        const totalLottieFrames = Math.max(1, anim.totalFrames || 60);
        const lottieFps = anim.frameRate || 30;
        const elapsedSec = Math.max(0, (frame - startFrame) / Math.max(1, fps));
        anim.goToAndStop((elapsedSec * lottieFps) % totalLottieFrames, true);
      } catch {
        // Graceful no-op if unavailable
      } finally {
        continueRender(handle);
      }
    })();
    return () => {
      cancelled = true;
      if (animRef.current) {
        try {
          animRef.current.destroy();
        } catch {}
        animRef.current = null;
      }
    };
  }, [stem]);

  useEffect(() => {
    const anim = animRef.current;
    if (!anim) return;
    const totalLottieFrames = Math.max(1, anim.totalFrames || 60);
    const lottieFps = anim.frameRate || 30;
    const elapsedSec = Math.max(0, (frame - startFrame) / Math.max(1, fps));
    anim.goToAndStop((elapsedSec * lottieFps) % totalLottieFrames, true);
  }, [frame, fps, startFrame]);

  return (
    <div
      ref={boxRef}
      style={{
        width: size,
        height: size,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    />
  );
};
