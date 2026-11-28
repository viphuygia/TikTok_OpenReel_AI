import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  Loop,
  OffthreadVideo,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { TransitionSeries, springTiming } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { slide } from '@remotion/transitions/slide';
import { wipe } from '@remotion/transitions/wipe';
import { flip } from '@remotion/transitions/flip';
import { Trail } from '@remotion/motion-blur';
import { evolvePath } from '@remotion/paths';
import { Star } from '@remotion/shapes';
import { loadProjectFonts } from '../../fonts';
import { resolveVisualTheme } from '../../themes';
import { TikTokVideoProps } from '../../types';
import { AsymmetricBox } from '../../primitives/AsymmetricBox';
import { KineticKaraoke } from '../../primitives/KineticKaraoke';
import { LivingVideoClip } from '../../primitives/LivingVideoClip';
import { StaggeredLayer } from '../../primitives/StaggeredLayer';
import { TwemojiText } from '../../primitives/TwemojiText';

loadProjectFonts();

const COLOR_FILTERS: Record<NonNullable<TikTokVideoProps['colorPreset']>, string> = {
  natural: 'contrast(1.04) saturate(1.08)',
  warm_film: 'contrast(1.07) saturate(1.14) sepia(0.08)',
  cool_vivid: 'contrast(1.09) saturate(1.16) hue-rotate(-4deg)',
};

const SWOOSH_PATH = 'M 18 28 Q 260 4 540 22 T 760 14';

const lottieJsonCache = new Map<string, any>();
let lottieLibPromise: Promise<any> | null = null;

function ensureLottieLib(): Promise<any> {
  if (typeof window === 'undefined') return Promise.resolve(null);
  if ((window as any).lottie) return Promise.resolve((window as any).lottie);
  if (!lottieLibPromise) {
    lottieLibPromise = new Promise((resolve) => {
      const sc = document.createElement('script');
      sc.src = staticFile('assets/lottie.min.js');
      sc.async = true;
      sc.onload = () => resolve((window as any).lottie || null);
      sc.onerror = () => resolve(null);
      document.head.appendChild(sc);
    });
  }
  return lottieLibPromise;
}

const FrameLockedLottieSticker: React.FC<{
  assetPath: string;
  localFrame: number;
  fps: number;
  size?: number;
}> = ({ assetPath, localFrame, fps, size = 132 }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const animRef = useRef<any>(null);
  const [fallbackImg, setFallbackImg] = useState(false);
  const [animReady, setAnimReady] = useState(false);

  const fileName = assetPath.split('/').pop() || '';
  const stem = fileName.replace(/\.(webp|gif|png|json)$/i, '');
  const jsonUrl = stem ? staticFile(`assets/lottie_stickers/${stem}.json`) : '';

  useEffect(() => {
    let cancelled = false;
    if (!stem || !jsonUrl) {
      setFallbackImg(true);
      return;
    }
    const handle = delayRender(`Loading Lottie sticker ${stem}`);

    const setup = async () => {
      try {
        const lottieLib = await ensureLottieLib();
        if (!lottieLib) throw new Error('lottie.min.js unavailable');
        let animData = lottieJsonCache.get(stem);
        if (!animData) {
          const resp = await fetch(jsonUrl);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          animData = await resp.json();
          lottieJsonCache.set(stem, animData);
        }
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = '';
        const anim = lottieLib.loadAnimation({
          container: containerRef.current,
          renderer: 'svg',
          loop: true,
          autoplay: false,
          animationData: JSON.parse(JSON.stringify(animData)),
        });
        animRef.current = anim;
        const fr = Number(anim.frameRate || animData.fr || 30);
        const tot = Math.max(1, Number(anim.totalFrames || animData.op || 60));
        const localSec = Math.max(0, localFrame / Math.max(1, fps));
        anim.goToAndStop((localSec * fr * 0.8) % tot, true);
        if (!cancelled) setAnimReady(true);
      } catch {
        if (!cancelled) setFallbackImg(true);
      } finally {
        continueRender(handle);
      }
    };

    setup();
    return () => {
      cancelled = true;
      if (animRef.current && typeof animRef.current.destroy === 'function') {
        try {
          animRef.current.destroy();
        } catch {}
      }
      animRef.current = null;
      setAnimReady(false);
    };
  }, [stem, jsonUrl]);

  useLayoutEffect(() => {
    const anim = animRef.current;
    if (!anim || !animReady) return;
    const fr = Number(anim.frameRate || 30);
    const tot = Math.max(1, Number(anim.totalFrames || 60));
    const localSec = Math.max(0, localFrame / Math.max(1, fps));
    anim.goToAndStop((localSec * fr * 0.8) % tot, true);
  }, [localFrame, fps, animReady]);

  if (fallbackImg) {
    return (
      <Img
        src={staticFile(assetPath)}
        style={{ width: size, height: size, objectFit: 'contain' }}
      />
    );
  }

  return (
    <div
      ref={containerRef}
      style={{
        width: size,
        height: size,
        filter: 'drop-shadow(0 10px 22px rgba(0,0,0,0.45))',
      }}
    />
  );
};

export const InnovationComposition: React.FC<TikTokVideoProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();

  const theme = resolveVisualTheme(props.visualTheme);
  const preset = props.innovationPreset || 'kinetic_pop';
  const baseFilter = COLOR_FILTERS[props.colorPreset || 'natural'] || 'none';
  const colorFilter =
    props.colorPreset && props.colorPreset !== 'natural'
      ? baseFilter
      : props.wildcardSpec
        ? 'contrast(1.07) saturate(1.18) brightness(1.02)'
        : baseFilter;
  const fontHeading = props.fontHeading || 'Baloo 2';
  const fontBrand = props.fontBrand || 'Montserrat Black';

  const clips = props.clips || [];
  const wc = props.wildcardSpec;
  const archetype =
    wc?.layoutArchetype ||
    (preset === 'magazine_split'
      ? 'editorial_zine'
      : preset === 'neon_pulse'
        ? 'tech_hud'
        : 'kinetic_poster');
  const motifKind = wc?.motifKind || (preset === 'neon_pulse' ? 'cyber_grid' : 'sparkle_burst');
  const accentCol = wc?.accentColor || theme.productColor || '#FFE500';
  const popPalette = wc?.popPalette && wc.popPalette.length > 0 ? wc.popPalette : ['#FF4D6D', '#FFE500', '#00F5D4', '#38BDF8', '#A855F7'];
  const stickerEvents = props.stickerDensity === 'off' ? [] : (wc?.stickerEvents || []);
  const iconDensity = props.iconDensity || 'balanced';
  const isWildcard = Boolean(wc);
  const transLevel = props.transitionLevel || 'balanced';
  const disableFlashShake = props.disableFlashShake !== false;
  const transFrames = transLevel === 'gentle' ? 6 : transLevel === 'balanced' ? 7 : 8;

  // Spotlight Hook (0 -> 3.6s): starts near center, settles upward after 1.1s
  const badgeStart = props.floralBadge?.start ?? 0;
  const badgeEnd = props.floralBadge?.end ?? 3.8;
  const badgeStartFrame = Math.max(0, Math.round(badgeStart * fps));
  const badgeDurationFrames = Math.max(30, Math.round((badgeEnd - badgeStart) * fps));
  const hookSettle = spring({
    frame: Math.max(0, frame - Math.round(fps * 1.1)),
    fps,
    config: { damping: 14, stiffness: 150, mass: 0.85 },
  });
  const dynamicHookTop = interpolate(hookSettle, [0, 1], [height * 0.34, height * (props.hookY || 0.16)]);
  const introBlur =
    frame < Math.round(fps * 1.3)
      ? interpolate(frame, [0, Math.round(fps * 0.9), Math.round(fps * 1.3)], [7, 4, 0], {
          extrapolateRight: 'clamp',
        })
      : 0;

  // Deduplicated USP checklist items from clips
  const uniqueUsps: string[] = [];
  for (const c of clips) {
    const p = String(c.featurePill || '').trim();
    if (p && !uniqueUsps.includes(p)) uniqueUsps.push(p);
    if (uniqueUsps.length >= 3) break;
  }

  const checklistStart = Math.round(durationInFrames * 0.24);
  const checklistDur = Math.max(45, Math.round(durationInFrames * 0.44));
  const ctaStartFrame = Math.round(durationInFrames * 0.82);
  const ctaDurationFrames = Math.max(30, durationInFrames - ctaStartFrame);

  const isMagazine = preset === 'magazine_split';
  const isNeon = preset === 'neon_pulse';

  const cardBackground = isNeon
    ? 'linear-gradient(135deg, rgba(10,12,28,0.9), rgba(67,16,112,0.88))'
    : isMagazine
      ? 'rgba(255, 255, 255, 0.96)'
      : theme.cardBg || 'linear-gradient(135deg, rgba(15,23,42,0.9), rgba(30,41,59,0.88))';

  const cardBorder = isNeon
    ? `3px solid ${theme.productColor}`
    : isMagazine
      ? '4px solid #0F172A'
      : theme.cardBorder || '2px solid rgba(255,255,255,0.35)';

  // Evolve SVG underline path during hook
  const drawProg = interpolate(frame, [6, 26], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const evolved = evolvePath(drawProg, SWOOSH_PATH);
  const starSpin = interpolate(frame, [0, 90], [0, 180]);

  const progressRatio = Math.min(1, Math.max(0, frame / Math.max(1, durationInFrames - 1)));
  const activeClipIdx = clips.findIndex(
    (c) => frame / fps >= c.startInTimeline && frame / fps <= c.startInTimeline + c.duration
  );
  const safeClipIdx = activeClipIdx >= 0 ? activeClipIdx : 0;
  const nextClip = clips.length > 1 ? clips[(safeClipIdx + 1) % clips.length] : undefined;
  const brandLabel = (props.floralBadge?.brand || 'TIKTOK SHOP').toUpperCase();
  const tickerText =
    wc?.tickerText ||
    `🔥 ${brandLabel} · ${(props.floralBadge?.productLine || 'SIÊU DEAL HOT').toUpperCase()} · GIỎ HÀNG GÓC TRÁI`;
  const tickerOffset = -((frame * 4.5) % 1400);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: props.transparentBg ? 'transparent' : '#050810',
        backgroundImage: !props.transparentBg && wc?.bgGradient ? wc.bgGradient : undefined,
      }}
    >
      {/* 0. Wildcard Kinetic Backdrop (visible around scaled/tilted frames) */}
      {!props.transparentBg && !props.badgeOnly && isWildcard && (
        <AbsoluteFill style={{ pointerEvents: 'none', overflow: 'hidden' }}>
          {archetype === 'kinetic_poster' && (
            <div
              style={{
                position: 'absolute',
                inset: -180,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-around',
                transform: 'rotate(-14deg)',
                opacity: 0.16,
              }}
            >
              {[0, 1, 2, 3, 4].map((row) => (
                <div
                  key={row}
                  style={{
                    whiteSpace: 'nowrap',
                    fontFamily: `'${fontBrand}', sans-serif`,
                    fontWeight: 900,
                    fontSize: 128,
                    letterSpacing: 8,
                    color: row % 2 === 0 ? accentCol : '#FFFFFF',
                    transform: `translateX(${((row % 2 === 0 ? -1 : 1) * (frame * 2.2)) % 420}px)`,
                  }}
                >
                  {`${brandLabel} • ${brandLabel} • ${brandLabel} • ${brandLabel}`}
                </div>
              ))}
            </div>
          )}

          {motifKind === 'cyber_grid' && (
            <svg width={width} height={height} style={{ position: 'absolute', inset: 0, opacity: 0.25 }}>
              {Array.from({ length: 12 }).map((_, i) => (
                <line
                  key={`v-${i}`}
                  x1={i * Math.round(width / 11)}
                  y1={0}
                  x2={i * Math.round(width / 11)}
                  y2={height}
                  stroke={accentCol}
                  strokeWidth={1.5}
                />
              ))}
              {Array.from({ length: 16 }).map((_, i) => {
                const yPos = ((i * 130 + frame * 2.5) % height);
                return (
                  <line
                    key={`h-${i}`}
                    x1={0}
                    y1={yPos}
                    x2={width}
                    y2={yPos}
                    stroke={accentCol}
                    strokeWidth={1.5}
                  />
                );
              })}
            </svg>
          )}
        </AbsoluteFill>
      )}

      {/* 1. Living Video Clips with real @remotion/transitions (or True 54/46 Split-Screen in bento_split!) */}
      {!props.transparentBg && !props.badgeOnly && clips.length > 0 && (
        <AbsoluteFill
          style={{
            filter: introBlur > 0.2 ? `blur(${introBlur.toFixed(1)}px)` : 'none',
            clipPath:
              frame < 16
                ? `circle(${interpolate(frame, [0, 16], [12, 125], { extrapolateRight: 'clamp' }).toFixed(1)}% at 50% 45%)`
                : undefined,
            transform: wc && archetype !== 'bento_split'
              ? `scale(${wc.frameScale ?? 1}) rotate(${wc.frameTiltDeg ?? 0}deg)`
              : undefined,
            borderRadius: wc?.frameRadius && archetype !== 'bento_split' ? wc.frameRadius : 0,
            border:
              archetype === 'polaroid_scrapbook'
                ? '18px solid #FAF8F5'
                : wc?.frameScale && wc.frameScale < 0.99 && archetype !== 'bento_split'
                  ? `5px solid ${wc.frameBorderColor || '#FFFFFF'}`
                  : undefined,
            paddingBottom: archetype === 'polaroid_scrapbook' ? 56 : 0,
            backgroundColor: archetype === 'polaroid_scrapbook' ? '#FAF8F5' : undefined,
            overflow: 'hidden',
            boxShadow: wc?.frameScale && wc.frameScale < 0.99 ? '0 30px 70px rgba(0,0,0,0.65)' : undefined,
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: archetype === 'bento_split' && nextClip ? '54%' : '100%',
              overflow: 'hidden',
            }}
          >
            <TransitionSeries>
              {clips.map((clip, idx) => {
                const hasNext = idx < clips.length - 1;
                const useTrans =
                  hasNext &&
                  (transLevel === 'energetic'
                    ? true
                    : transLevel === 'balanced'
                      ? idx % 2 === 0
                      : idx % 3 === 1);
                const isLast = idx === clips.length - 1;
                const baseDur = Math.max(18, Math.round(clip.duration * fps));
                const seqDur = (useTrans ? baseDur + transFrames : baseDur) + (isLast ? 15 : 0);
                const transPres =
                  transLevel === 'gentle'
                    ? idx % 2 === 0
                      ? fade()
                      : slide({ direction: 'from-right' })
                    : transLevel === 'balanced'
                      ? idx % 4 === 0
                        ? slide({ direction: 'from-right' })
                        : wipe({ direction: 'from-left' })
                      : idx % 3 === 0
                        ? slide({ direction: 'from-right' })
                        : idx % 3 === 1
                          ? wipe({ direction: 'from-left' })
                          : slide({ direction: 'from-bottom' });

                return (
                  <React.Fragment key={clip.id || idx}>
                    <TransitionSeries.Sequence durationInFrames={seqDur}>
                      <LivingVideoClip
                        clip={clip}
                        clipIdx={idx}
                        cameraIntensity={props.cameraIntensity || 'dynamic_ai'}
                        colorFilter={colorFilter}
                        disableFlashShake={disableFlashShake}
                      />
                    </TransitionSeries.Sequence>
                    {useTrans && (
                      <TransitionSeries.Transition
                        presentation={transPres as never}
                        timing={springTiming({ config: { damping: 16, stiffness: 200 }, durationInFrames: transFrames })}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </TransitionSeries>
          </div>

          {/* Bottom 46% Split-Screen Secondary Angle + Kinetic Divider Banner */}
          {archetype === 'bento_split' && nextClip && (
            <>
              <div
                style={{
                  position: 'absolute',
                  top: '54%',
                  left: 0,
                  right: 0,
                  height: '46%',
                  overflow: 'hidden',
                  borderTop: `6px solid ${accentCol}`,
                }}
              >
                <Loop durationInFrames={Math.max(18, Math.round(nextClip.duration * fps))}>
                  <LivingVideoClip
                    clip={nextClip}
                    clipIdx={(safeClipIdx + 1) % clips.length}
                    cameraIntensity="energetic"
                    colorFilter={colorFilter}
                    disableFlashShake
                  />
                </Loop>
              </div>
              <div
                style={{
                  position: 'absolute',
                  top: '51.5%',
                  left: -20,
                  right: -20,
                  height: 68,
                  background: accentCol,
                  transform: 'rotate(-1.8deg)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 10px 28px rgba(0,0,0,0.55)',
                  zIndex: 5,
                }}
              >
                <span
                  style={{
                    fontFamily: `'${fontBrand}', sans-serif`,
                    fontWeight: 900,
                    fontSize: 30,
                    color: '#090D16',
                    letterSpacing: 1.5,
                  }}
                >
                  {`⚡ ${brandLabel} · ${uniqueUsps[0] || props.floralBadge?.productLine || 'REVIEW THỰC TẾ'}`}
                </span>
              </div>
            </>
          )}
        </AbsoluteFill>
      )}

      {/* Cinematic top/bottom vignette + optional Wildcard Cinema Letterbox */}
      {!props.transparentBg && (
        <AbsoluteFill
          style={{
            background:
              'linear-gradient(180deg, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.0) 28%, rgba(0,0,0,0.0) 60%, rgba(0,0,0,0.65) 100%)',
            pointerEvents: 'none',
          }}
        />
      )}
      {!props.transparentBg && wc && wc.letterboxPx > 0 && (
        <>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: wc.letterboxPx, background: '#050810', pointerEvents: 'none' }} />
          <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: wc.letterboxPx, background: '#050810', pointerEvents: 'none' }} />
        </>
      )}

      {/* 2. Procedural Vector Motifs & Layout Archetype Graphics */}
      {!props.badgeOnly && !props.transparentBg && (
        <AbsoluteFill style={{ pointerEvents: 'none' }}>
          {/* Polaroid Masking Tape Corners */}
          {isWildcard && archetype === 'polaroid_scrapbook' && (
            <>
              <div
                style={{
                  position: 'absolute',
                  top: 120,
                  left: 70,
                  width: 150,
                  height: 38,
                  background: 'rgba(253, 224, 71, 0.72)',
                  transform: 'rotate(-24deg)',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  top: 125,
                  right: 70,
                  width: 150,
                  height: 38,
                  background: 'rgba(253, 224, 71, 0.72)',
                  transform: 'rotate(22deg)',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                }}
              />
            </>
          )}

          {/* Rotating Authentic Starburst Stamp Seal + Hand-Drawn SVG Pointer during USP phase */}
          <div
            style={{
              position: 'absolute',
              top: 320,
              right: 28,
              width: 136,
              height: 136,
              transform: `rotate(${frame * 1.1}deg)`,
              opacity: 0.92,
            }}
          >
            <Star points={12} innerRadius={52} outerRadius={66} fill={accentCol} />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                transform: `rotate(${-frame * 1.1}deg)`,
                color: '#090D16',
                fontFamily: `'${fontBrand}', sans-serif`,
                fontWeight: 900,
                fontSize: 17,
                lineHeight: 1.1,
                textAlign: 'center',
              }}
            >
              <span>TIKTOK</span>
              <span>SHOP · GỢI Ý</span>
            </div>
          </div>

          {frame >= checklistStart && frame <= checklistStart + checklistDur && (
            <svg width={220} height={140} viewBox="0 0 220 140" style={{ position: 'absolute', top: 690, right: 36, overflow: 'visible' }}>
              <path
                d="M 190 16 Q 110 8 42 86 M 42 86 L 72 82 M 42 86 L 48 56"
                fill="none"
                stroke={accentCol}
                strokeWidth={7}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeDasharray={320}
                strokeDashoffset={interpolate(frame, [checklistStart, checklistStart + 22], [320, 0], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })}
              />
            </svg>
          )}

          {/* Tech HUD Viewfinder Brackets, Scanline & Live Audio Waveform */}
          {(archetype === 'tech_hud' || isNeon) && (
            <>
              <div
                style={{
                  position: 'absolute',
                  top: 56,
                  left: 28,
                  width: 64,
                  height: 64,
                  borderTop: `5px solid ${accentCol}`,
                  borderLeft: `5px solid ${accentCol}`,
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  top: 56,
                  right: 28,
                  width: 64,
                  height: 64,
                  borderTop: `5px solid ${accentCol}`,
                  borderRight: `5px solid ${accentCol}`,
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  bottom: 66,
                  left: 28,
                  width: 64,
                  height: 64,
                  borderBottom: `5px solid ${accentCol}`,
                  borderLeft: `5px solid ${accentCol}`,
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  bottom: 66,
                  right: 28,
                  width: 64,
                  height: 64,
                  borderBottom: `5px solid ${accentCol}`,
                  borderRight: `5px solid ${accentCol}`,
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  top: 76,
                  right: 48,
                  padding: '6px 16px',
                  borderRadius: 10,
                  background: 'rgba(9, 13, 22, 0.78)',
                  border: `2px solid ${accentCol}`,
                  color: accentCol,
                  fontFamily: `'${fontBrand}', sans-serif`,
                  fontWeight: 800,
                  fontSize: 20,
                  letterSpacing: 1.4,
                }}
              >
                ● REC · CAM 0{safeClipIdx + 1}
              </div>
              {isWildcard && (
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    right: 0,
                    top: `${((frame * 5) % height)}px`,
                    height: 3,
                    background: `linear-gradient(90deg, transparent, ${accentCol}, transparent)`,
                    opacity: 0.45,
                  }}
                />
              )}
              {/* Animated 16-bar Audio Equalizer */}
              <div
                style={{
                  position: 'absolute',
                  bottom: 118,
                  right: 52,
                  display: 'flex',
                  alignItems: 'flex-end',
                  gap: 6,
                  height: 54,
                }}
              >
                {Array.from({ length: 16 }).map((_, bi) => {
                  const barH = 12 + Math.abs(Math.sin(frame * 0.25 + bi * 0.7)) * 38;
                  return (
                    <div
                      key={bi}
                      style={{
                        width: 7,
                        height: barH,
                        borderRadius: 4,
                        background: accentCol,
                        opacity: 0.85,
                      }}
                    />
                  );
                })}
              </div>
            </>
          )}

          {/* Film Grain / Light Leak / Texture Overlay */}
          {(() => {
            const rawOv = props.overlayEffect || 'auto';
            const ovFile =
              rawOv !== 'auto'
                ? rawOv
                : archetype === 'tech_hud'
                  ? 'grid_hud_overlay.png'
                  : archetype === 'polaroid_scrapbook' || archetype === 'editorial_zine'
                    ? 'paper_texture_warm.png'
                    : props.colorPreset === 'warm_film'
                      ? 'light_leak_warm.mp4'
                      : props.colorPreset === 'cool_vivid'
                        ? 'light_leak_cool.mp4'
                        : 'none';
            if (!ovFile || ovFile === 'none') return null;
            const isVideoOv = ovFile.endsWith('.mp4') || ovFile.endsWith('.webm');
            const isPaperOv = ovFile.startsWith('paper_');
            return (
              <AbsoluteFill
                style={{
                  pointerEvents: 'none',
                  mixBlendMode: isPaperOv ? 'overlay' : 'screen',
                  opacity: isPaperOv ? 0.16 : ovFile.includes('grain') ? 0.24 : 0.30,
                }}
              >
                {isVideoOv ? (
                  <Loop durationInFrames={ovFile.includes('grain') ? 120 : 180}>
                    <OffthreadVideo
                      src={staticFile(`assets/overlays/${ovFile}`)}
                      muted
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  </Loop>
                ) : (
                  <Img
                    src={staticFile(`assets/overlays/${ovFile}`)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                )}
              </AbsoluteFill>
            );
          })()}

          {/* Editorial Magazine Masthead & Scene Index */}
          {(archetype === 'editorial_zine' || isMagazine) && (
            <>
              <div
                style={{
                  position: 'absolute',
                  top: 52,
                  left: 36,
                  right: 36,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  borderBottom: `2px solid ${accentCol}`,
                  paddingBottom: 10,
                }}
              >
                <span
                  style={{
                    fontFamily: `'${fontBrand}', sans-serif`,
                    fontWeight: 900,
                    fontSize: 22,
                    letterSpacing: 2,
                    color: '#FFFFFF',
                    textShadow: '0 2px 8px rgba(0,0,0,0.8)',
                  }}
                >
                  {`ISSUE #0${safeClipIdx + 1} · ${brandLabel}`}
                </span>
                <span
                  style={{
                    fontFamily: `'${fontHeading}', sans-serif`,
                    fontWeight: 900,
                    fontSize: 22,
                    color: accentCol,
                  }}
                >
                  TIKTOK EDIT 2026
                </span>
              </div>
              {isWildcard && (
                <div
                  style={{
                    position: 'absolute',
                    top: 620,
                    left: -130,
                    transform: 'rotate(-90deg)',
                    fontFamily: `'${fontBrand}', sans-serif`,
                    fontWeight: 800,
                    fontSize: 22,
                    letterSpacing: 4,
                    color: accentCol,
                    opacity: 0.8,
                  }}
                >
                  VERIFIED PRODUCT REVIEW ★
                </div>
              )}
            </>
          )}

          {/* Floating Product-Themed Vector Motifs (Bubbles, Leaves, Sparkles, Wave) */}
          {isWildcard && (motifKind === 'bubbles_ice' || motifKind === 'botanical_leaf' || motifKind === 'geometric_orbit') && (
            <svg width={width} height={height} style={{ position: 'absolute', inset: 0 }}>
              {motifKind === 'bubbles_ice' &&
                [0, 1, 2, 3, 4, 5].map((i) => {
                  const cx = i % 2 === 0 ? 75 + i * 24 : (width - 100) - i * 22;
                  const cy = (height - 70) - ((frame * (2.6 + i * 0.4) + i * 290) % Math.max(600, height - 120));
                  const r = 16 + (i % 3) * 10;
                  return (
                    <circle
                      key={i}
                      cx={cx}
                      cy={cy}
                      r={r}
                      fill="rgba(255,255,255,0.14)"
                      stroke={popPalette[i % popPalette.length]}
                      strokeWidth={3}
                    />
                  );
                })}
              {motifKind === 'botanical_leaf' &&
                [0, 1, 2, 3].map((i) => {
                  const lx = i % 2 === 0 ? 74 : 996;
                  const ly = 360 + i * 320 + Math.sin(frame * 0.06 + i) * 26;
                  const rot = Math.sin(frame * 0.05 + i) * 24 + (i % 2 === 0 ? -20 : 20);
                  return (
                    <path
                      key={i}
                      d="M 0 -28 C 22 -14 22 14 0 28 C -22 14 -22 -14 0 -28 Z"
                      transform={`translate(${lx}, ${ly}) rotate(${rot})`}
                      fill={popPalette[i % popPalette.length]}
                      opacity={0.62}
                    />
                  );
                })}
              {motifKind === 'geometric_orbit' && (
                <g transform={`translate(930, 320) rotate(${frame * 1.4})`} opacity={0.55}>
                  <circle cx={0} cy={0} r={58} fill="none" stroke={accentCol} strokeWidth={3} strokeDasharray="12 10" />
                  <circle cx={58} cy={0} r={9} fill="#FFE500" />
                </g>
              )}
            </svg>
          )}

          {/* Gemini AI-Generated Multi-Color SVG Overlay */}
          {isWildcard && wc?.customSvgOverlay && (
            <AbsoluteFill
              style={{ pointerEvents: 'none', opacity: 0.82 }}
              dangerouslySetInnerHTML={{ __html: wc.customSvgOverlay }}
            />
          )}

          {/* Multi-Color Confetti: opt-in only (disabled by default for clean creator look) */}
          {props.overlayEffect === 'bokeh_sparkle.mp4' && (frame < Math.round(fps * 3.2) || frame >= ctaStartFrame) && (
            <AbsoluteFill style={{ pointerEvents: 'none', overflow: 'hidden' }}>
              {Array.from({ length: 18 }).map((_, ci) => {
                const localF = frame < Math.round(fps * 3.2) ? frame : frame - ctaStartFrame;
                const px = ((ci * 137 + 40) % 980) + 45;
                const py = ((ci * 97 + localF * (8 + (ci % 4) * 3)) % 1800);
                const col = popPalette[ci % popPalette.length];
                return (
                  <div
                    key={`cf-${ci}`}
                    style={{
                      position: 'absolute',
                      left: px,
                      top: py,
                      width: ci % 2 === 0 ? 16 : 12,
                      height: ci % 2 === 0 ? 16 : 24,
                      borderRadius: ci % 3 === 0 ? 999 : 4,
                      background: col,
                      transform: `rotate(${localF * (5 + ci % 5)}deg)`,
                      opacity: 0.85,
                    }}
                  />
                );
              })}
            </AbsoluteFill>
          )}

          {/* Dynamic Animated WebP Stickers & Messenger-Style Chat Bubbles */}
          {stickerEvents.map((st, si) => {
            const sStart = Math.max(0, Math.round(st.start * fps));
            const sDur = Math.max(24, Math.round(st.duration * fps));
            if (frame < sStart || frame > sStart + sDur) return null;
            const popIn = spring({
              frame: frame - sStart,
              fps,
              config: { damping: 10, stiffness: 220, mass: 0.65 },
            });
            const popOut =
              frame > sStart + sDur - 8
                ? interpolate(frame, [sStart + sDur - 8, sStart + sDur], [1, 0], { extrapolateRight: 'clamp' })
                : 1;
            const sc = interpolate(popIn, [0, 1], [0.2, 1]) * popOut;
            const isAnimStk = st.styleKind === 'animated_sticker' && st.stickerAsset;
            const hookEndSec = props.floralBadge?.enabled ? (props.floralBadge?.end ?? 3.8) : 0;
            const safeYPct = st.start < hookEndSec && st.yPct < 0.40 ? 0.42 : st.yPct;
            if (isAnimStk && st.stickerAsset) {
              return (
                <div
                  key={`stk-${si}`}
                  style={{
                    position: 'absolute',
                    left: `${(st.xPct * 100).toFixed(1)}%`,
                    top: `${(safeYPct * 100).toFixed(1)}%`,
                    transform: `scale(${sc.toFixed(3)}) rotate(${st.rotateDeg ?? (si % 2 === 0 ? -6 : 6)}deg)`,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 4,
                    pointerEvents: 'none',
                  }}
                >
                  <FrameLockedLottieSticker
                    assetPath={st.stickerAsset}
                    localFrame={Math.max(0, frame - sStart)}
                    fps={fps}
                    size={132}
                  />
                  <span
                    style={{
                      padding: '4px 14px',
                      borderRadius: 999,
                      background: st.bg || popPalette[si % popPalette.length],
                      border: '3px solid #FFFFFF',
                      fontFamily: `'${fontBrand}', sans-serif`,
                      fontWeight: 900,
                      fontSize: 19,
                      color: '#090D16',
                      boxShadow: '0 8px 20px rgba(0,0,0,0.45)',
                    }}
                  >
                    {st.label}
                  </span>
                </div>
              );
            }
            return (
                <div
                  key={`stk-${si}`}
                  style={{
                    position: 'absolute',
                    left: `${(st.xPct * 100).toFixed(1)}%`,
                    top: `${(safeYPct * 100).toFixed(1)}%`,
                    transform: `scale(${sc.toFixed(3)}) rotate(${st.rotateDeg ?? (si % 2 === 0 ? -5 : 5)}deg)`,
                    padding: '12px 22px',
                  borderRadius: '24px 24px 24px 6px',
                  background: st.bg || popPalette[si % popPalette.length],
                  border: '3.5px solid #FFFFFF',
                  boxShadow: '0 14px 32px rgba(0,0,0,0.45)',
                  pointerEvents: 'none',
                }}
              >
                <span
                  style={{
                    fontFamily: `'${fontBrand}', sans-serif`,
                    fontWeight: 900,
                    fontSize: 22,
                    color: '#090D16',
                    letterSpacing: 0.5,
                  }}
                >
                  {st.label}
                </span>
              </div>
            );
          })}

          {/* Breaking News / Promo Marquee Ticker Ribbon */}
          {isWildcard && (archetype === 'bento_split' || wc?.hookLayout === 'breaking_ticker') && (
            <div
              style={{
                position: 'absolute',
                bottom: 42,
                left: 0,
                right: 0,
                height: 48,
                background: accentCol,
                display: 'flex',
                alignItems: 'center',
                overflow: 'hidden',
                boxShadow: '0 -4px 18px rgba(0,0,0,0.45)',
              }}
            >
              <div
                style={{
                  whiteSpace: 'nowrap',
                  fontFamily: `'${fontBrand}', sans-serif`,
                  fontWeight: 900,
                  fontSize: 24,
                  color: '#090D16',
                  transform: `translateX(${tickerOffset}px)`,
                }}
              >
                {`${tickerText}   ★   ${tickerText}   ★   ${tickerText}`}
              </div>
            </div>
          )}

          {/* Rating badge removed for TikTok Shop policy compliance */}
        </AbsoluteFill>
      )}

      {/* 2B. Segmented Story Progress Bar (one segment per clip) */}
      {!props.badgeOnly && (
        <div
          style={{
            position: 'absolute',
            top: 24,
            left: 36,
            right: 36,
            display: 'flex',
            gap: 8,
            pointerEvents: 'none',
          }}
        >
          {(clips.length > 0 ? clips : [{ duration: props.durationSec || 25, startInTimeline: 0 }]).map((c, idx) => {
            const cStart = c.startInTimeline || 0;
            const cDur = Math.max(0.5, c.duration || 2);
            const curT = progressRatio * (props.durationSec || 25);
            const fillPct =
              curT >= cStart + cDur
                ? 100
                : curT <= cStart
                  ? 0
                  : ((curT - cStart) / cDur) * 100;
            return (
              <div
                key={idx}
                style={{
                  flex: cDur,
                  height: activeClipIdx === idx ? 9 : 6,
                  borderRadius: 999,
                  backgroundColor: 'rgba(255,255,255,0.22)',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${fillPct.toFixed(1)}%`,
                    height: '100%',
                    background: theme.progressGradient,
                  }}
                />
              </div>
            );
          })}
        </div>
      )}

      {/* 3. Spotlight Kinetic Hook Card with Motion-Blur Trail & Evolving SVG Swoosh */}
      {props.floralBadge?.enabled && (
        <Sequence from={badgeStartFrame} durationInFrames={badgeDurationFrames}>
          <div
            style={{
              position: 'absolute',
              top: dynamicHookTop,
              left: 48,
              right: 48,
              transform: 'translateY(-50%)',
              display: 'flex',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            {(() => {
              const hookBox = (
              <AsymmetricBox totalFrames={badgeDurationFrames}>
                <div
                  style={{
                    position: 'relative',
                    background: cardBackground,
                    border: cardBorder,
                    borderRadius: isMagazine ? 16 : 30,
                    padding: '26px 36px 22px',
                    boxShadow: isNeon
                      ? `0 0 42px ${theme.productColor}66, 0 22px 48px rgba(0,0,0,0.6)`
                      : '0 24px 52px rgba(0,0,0,0.52)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 10,
                    minWidth: 740,
                    maxWidth: 940,
                  }}
                >
                  {/* Animated Star sparkles from @remotion/shapes */}
                  <div style={{ position: 'absolute', top: -18, right: 24, transform: `rotate(${starSpin}deg)` }}>
                    <Star points={4} innerRadius={8} outerRadius={20} fill={theme.productColor} />
                  </div>
                  <div style={{ position: 'absolute', bottom: -14, left: 26, transform: `rotate(${-starSpin}deg)` }}>
                    <Star points={4} innerRadius={6} outerRadius={16} fill="#FFE500" />
                  </div>

                  <StaggeredLayer delayFrames={0} offsetY={16}>
                    <div
                      style={{
                        background: theme.topTagBg || theme.ctaBg,
                        color: theme.topTagColor || '#FFFFFF',
                        fontFamily: `'${fontBrand}', sans-serif`,
                        fontWeight: 900,
                        fontSize: 28,
                        letterSpacing: 1.6,
                        padding: '6px 22px',
                        borderRadius: 999,
                        textTransform: 'uppercase',
                      }}
                    >
                      {props.floralBadge.brand || 'REVIEW CHÂN THẬT'}
                    </div>
                  </StaggeredLayer>

                  <StaggeredLayer delayFrames={4} offsetY={22}>
                    <div
                      style={{
                        fontFamily: `'${fontHeading}', sans-serif`,
                        fontWeight: 900,
                        fontSize: 66,
                        lineHeight: 1.06,
                        textAlign: 'center',
                        color: isMagazine ? '#0F172A' : theme.productColor,
                        textShadow: isMagazine ? 'none' : '0 4px 16px rgba(0,0,0,0.7)',
                      }}
                    >
                      {props.floralBadge.productLine || props.title}
                    </div>
                  </StaggeredLayer>

                  {/* Live-drawn SVG swoosh underline (@remotion/paths) */}
                  <svg width={780} height={34} viewBox="0 0 780 34" style={{ marginTop: -4, overflow: 'visible' }}>
                    <path
                      d={SWOOSH_PATH}
                      fill="none"
                      stroke={theme.productColor}
                      strokeWidth={6}
                      strokeLinecap="round"
                      strokeDasharray={evolved.strokeDasharray}
                      strokeDashoffset={evolved.strokeDashoffset}
                    />
                  </svg>

                  {props.floralBadge.category && (
                    <StaggeredLayer delayFrames={8} offsetY={14}>
                      <div
                        style={{
                          fontFamily: `'${fontHeading}', sans-serif`,
                          fontWeight: 800,
                          fontSize: 34,
                          color: isMagazine ? '#334155' : '#FFFFFF',
                        }}
                      >
                        {props.floralBadge.category}
                      </div>
                    </StaggeredLayer>
                  )}
                </div>
              </AsymmetricBox>
              );
              return disableFlashShake ? hookBox : <Trail layers={3} lagInFrames={0.45} trailOpacity={0.35}>{hookBox}</Trail>;
            })()}
          </div>
        </Sequence>
      )}

      {/* 4. Bento USP Checklist (Sequential Green Checkmarks) */}
      {!props.badgeOnly && uniqueUsps.length > 0 && (
        <Sequence from={checklistStart} durationInFrames={checklistDur}>
          <div
            style={{
              position: 'absolute',
              top: Math.round(height * 0.24),
              left: 46,
              pointerEvents: 'none',
            }}
          >
            <AsymmetricBox totalFrames={checklistDur} enterOffsetY={24} exitOffsetY={-20}>
              <div
                style={{
                  background: 'rgba(9, 13, 22, 0.78)',
                  backdropFilter: 'blur(10px)',
                  border: `2px solid ${theme.productColor}66`,
                  borderRadius: 22,
                  padding: '14px 20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  boxShadow: '0 14px 32px rgba(0,0,0,0.45)',
                }}
              >
                {uniqueUsps.map((usp, idx) => {
                  const itemDelay = idx * 18;
                  const localF = Math.max(0, frame - checklistStart - itemDelay);
                  const pop = spring({
                    frame: localF,
                    fps,
                    config: { damping: 14, stiffness: 210, mass: 0.6 },
                  });
                  const checked = localF > 6;
                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                        opacity: interpolate(pop, [0, 1], [0, 1]),
                        transform: `translateX(${interpolate(pop, [0, 1], [-24, 0])}px)`,
                      }}
                    >
                      <span
                        style={{
                          width: 30,
                          height: 30,
                          borderRadius: 999,
                          background: checked ? '#10B981' : 'rgba(255,255,255,0.18)',
                          color: '#FFFFFF',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 900,
                          fontSize: 18,
                        }}
                      >
                        ✓
                      </span>
                      <span
                        style={{
                          fontFamily: `'${fontHeading}', sans-serif`,
                          fontWeight: 800,
                          fontSize: 28,
                          color: '#FFFFFF',
                        }}
                      >
                        {iconDensity === 'expressive' ? <TwemojiText text={usp} iconSize={28} /> : usp}
                      </span>
                    </div>
                  );
                })}
              </div>
            </AsymmetricBox>
          </div>
        </Sequence>
      )}

      {/* 5. Asymmetric Callout Banners */}
      {!props.badgeOnly &&
        (props.callouts || [])
          .filter((c) => {
            if (c.id === 'callout_cta') return false;
            if (props.floralBadge?.enabled && (c.id === 'callout_hook' || c.start < (props.floralBadge?.end ?? 3.8) - 0.2)) {
              return false;
            }
            return true;
          })
          .map((c, idx) => {
          const from = Math.max(0, Math.round(c.start * fps));
          const dur = Math.max(20, Math.round((c.end - c.start) * fps));
          const topPx = Math.round(height * (c.y ?? 0.42));
          return (
            <Sequence key={c.id || idx} from={from} durationInFrames={dur}>
              <div
                style={{
                  position: 'absolute',
                  top: topPx,
                  left: 44,
                  right: 44,
                  transform: 'translateY(-50%)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  pointerEvents: 'none',
                }}
              >
                <AsymmetricBox totalFrames={dur}>
                  {c.lines.map((line, lIdx) => (
                    <div
                      key={lIdx}
                      style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        justifyContent: 'center',
                        gap: 10,
                        fontFamily: `'${fontHeading}', sans-serif`,
                        fontWeight: 900,
                        fontSize: (c.fontSize || 50) + 4,
                        lineHeight: 1.15,
                        WebkitTextStroke: '8px #090D16',
                        paintOrder: 'stroke fill',
                      }}
                    >
                      {line.tokens.map((tk, tIdx) => (
                        <span
                          key={tIdx}
                          style={{
                            color: tk.color || '#FFFFFF',
                            textShadow: '0 4px 12px rgba(0,0,0,0.9)',
                          }}
                        >
                          {tk.text}
                        </span>
                      ))}
                    </div>
                  ))}
                </AsymmetricBox>
              </div>
            </Sequence>
          );
        })}

      {/* 6. Semantic Karaoke Subtitles (Stable Line Geometry) */}
      {!props.badgeOnly && (
        <KineticKaraoke
          words={props.words || []}
          subtitleY={wc?.subtitleY || props.subtitleY || 0.73}
          activeColor={wc?.accentColor || props.subtitleActiveColor || '#FFE500'}
          pillColor={wc?.accentColor || (isNeon ? '#7C3AED' : '#E11D48')}
          variant={wc?.subtitleVariant || 'clean_stroke'}
          fontHeading={fontHeading}
          subtitleLang={props.subtitleLang}
          enSubtitles={props.enSubtitles}
        />
      )}

      {/* 7. Bottom TikTok Shop CTA Pill */}
      {!props.badgeOnly && props.disclaimerText && frame < Math.round(fps * 4.2) ? (() => {
        const discFrames = Math.round(fps * 4.2);
        const discAlpha = interpolate(frame, [0, 8, Math.max(12, discFrames - 10), discFrames], [0, 1, 1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        return (
          <div
            style={{
              position: 'absolute',
              top: (props.aspectRatio === '16:9') ? 22 : '4.2%',
              left: 28,
              right: 28,
              display: 'flex',
              justifyContent: 'center',
              opacity: discAlpha,
              zIndex: 48,
              pointerEvents: 'none',
            }}
          >
            <div
              style={{
                backgroundColor: 'rgba(15, 23, 42, 0.88)',
                border: `2px solid ${wc?.accentColor || '#F59E0B'}`,
                borderRadius: 999,
                padding: '9px 22px',
                boxShadow: '0 10px 26px rgba(0,0,0,0.5)',
                color: '#FEF3C7',
                fontFamily: `'${fontHeading}', sans-serif`,
                fontWeight: 700,
                fontSize: (props.aspectRatio === '16:9') ? 22 : 24,
                lineHeight: 1.3,
                textAlign: 'center',
                maxWidth: '94%',
              }}
            >
              {props.disclaimerText}
            </div>
          </div>
        );
      })() : null}

      {!props.badgeOnly && (
        <Sequence from={ctaStartFrame} durationInFrames={ctaDurationFrames}>
          <div style={{ position: 'absolute', bottom: 220, left: 52, pointerEvents: 'none' }}>
            <AsymmetricBox totalFrames={ctaDurationFrames} enterOffsetY={24} exitOffsetY={16}>
              <div
                style={{
                  background: wc?.accentColor ? wc.accentColor : theme.ctaBg,
                  border: wc?.frameBorderColor ? `2px solid ${wc.frameBorderColor}` : theme.ctaBorder,
                  color: wc?.textColor || '#FFFFFF',
                  fontFamily: `'${fontHeading}', sans-serif`,
                  fontWeight: 900,
                  fontSize: 32,
                  padding: '12px 26px',
                  borderRadius: 999,
                  boxShadow: '0 12px 28px rgba(0,0,0,0.48)',
                  transform: disableFlashShake ? 'none' : `scale(${1 + Math.sin(frame * 0.24) * 0.035})`,
                }}
              >
                <TwemojiText text={wc?.ctaLabel || '🛒 Giỏ Hàng Góc Trái'} iconSize={34} />
              </div>
            </AsymmetricBox>
          </div>
        </Sequence>
      )}

      {/* 8. Audio Tracks (TTS + BGM + SFX) */}
      {!props.badgeOnly && props.voiceSrc && <Audio src={staticFile(props.voiceSrc)} volume={1.0} />}
      {!props.badgeOnly && props.bgmSrc && (
        <Audio
          src={staticFile(props.bgmSrc)}
          loop
          volume={(f) => {
            const base = (props.bgmVolume ?? 0.14) * 0.85;
            const fadeIn = interpolate(f, [0, 15], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            const fadeOutStart = Math.max(0, durationInFrames - Math.round(fps * 1.2));
            const fadeOut = interpolate(f, [fadeOutStart, durationInFrames], [1, 0.08], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            return base * fadeIn * fadeOut;
          }}
        />
      )}
      {!props.badgeOnly &&
        (props.sfxEvents || []).map((sfx, idx) => (
          <Sequence
            key={sfx.id || idx}
            from={Math.max(0, Math.round(sfx.start * fps))}
            durationInFrames={Math.max(8, Math.round(sfx.duration * fps))}
          >
            <Audio src={staticFile(sfx.src)} volume={sfx.volume ?? props.sfxVolume ?? 0.5} />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
};
