import React from 'react';
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { loadProjectFonts } from './fonts';
import { FloralHookBadge } from './components/FloralHookBadge';
import { MulticolorCallout } from './components/MulticolorCallout';
import { KaraokeSubtitles } from './components/KaraokeSubtitles';
import { SharedLottieSticker, resolveLottieStem } from './components/SharedLottieSticker';
import { TikTokVideoProps, VideoClipItem } from './types';
import { VisualThemeTokens, resolveVisualTheme } from './themes';

loadProjectFonts();

const ClipLayer: React.FC<{
  clip: VideoClipItem;
  clipIdx: number;
  cameraIntensity?: TikTokVideoProps['cameraIntensity'];
  creativeMode?: TikTokVideoProps['creativeMode'];
  layoutStyle?: TikTokVideoProps['layoutStyle'];
  colorPreset?: TikTokVideoProps['colorPreset'];
  disableFlashShake?: boolean;
  fontHeading?: string;
  theme: VisualThemeTokens;
}> = ({
  clip,
  clipIdx,
  cameraIntensity = 'dynamic_ai',
  creativeMode = 'breakthrough_ai',
  layoutStyle = 'full',
  colorPreset = 'natural',
  disableFlashShake = true,
  fontHeading = 'Baloo 2',
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const totalFrames = Math.max(15, Math.round(clip.duration * fps));
  const mult = cameraIntensity === 'subtle' ? 0.55 : cameraIntensity === 'energetic' ? 1.35 : 1.0;

  const mode = clip.zoomMode || 'push_in';
  let baseScale = 1.0;

  if (mode === 'punch_in') {
    const punchSpring = spring({
      frame,
      fps,
      config: { damping: 12, stiffness: 195, mass: 0.7 },
    });
    const targetPeak = 1 + Math.max(0.14, (clip.zoomTo ?? 1.2) - 1) * mult;
    const drift = interpolate(frame, [10, totalFrames], [0, 0.03 * mult], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
    baseScale = interpolate(punchSpring, [0, 1], [1.0, targetPeak]) + drift;
  } else if (mode === 'zoom_out') {
    const rawFrom = (clip.zoomFrom ?? 1.2) > 1.06 ? (clip.zoomFrom ?? 1.2) : 1.2;
    const zStart = 1 + (rawFrom - 1) * mult;
    const zEnd = 1 + Math.max(0.0, (clip.zoomTo ?? 1.02) - 1) * 0.5;
    baseScale = interpolate(frame, [0, totalFrames], [zStart, zEnd], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
  } else if (mode === 'in_out') {
    const midFrame = Math.max(8, Math.round(totalFrames * 0.5));
    const peak = 1 + Math.max(0.14, (clip.zoomTo ?? 1.17) - 1) * mult;
    baseScale = interpolate(frame, [0, midFrame, totalFrames], [1.0, peak, 1.02], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
  } else {
    // push_in or ken_burns
    const zFrom = 1 + Math.max(0.0, (clip.zoomFrom ?? 1.0) - 1) * mult;
    const zTo = 1 + Math.max(0.12, (clip.zoomTo ?? 1.16) - 1) * mult;
    baseScale = interpolate(frame, [0, totalFrames], [zFrom, zTo], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
  }

  const panX = clip.panX
    ? interpolate(frame, [0, totalFrames], [0, clip.panX * mult], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      })
    : 0;
  const panY = clip.panY
    ? interpolate(frame, [0, totalFrames], [0, clip.panY * mult], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      })
    : 0;

  const slideOffset =
    clip.transitionType === 'slide'
      ? interpolate(frame, [0, 8], [160, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
      : 0;

  const transZoomBurst =
    clip.transitionType === 'zoom' && frame < 7
      ? interpolate(frame, [0, 7], [1.22, 1.0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
      : 1.0;

  const flashOpacity =
    !disableFlashShake && clip.transitionType === 'flash'
      ? interpolate(frame, [0, 6], [0.42, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
      : 0;

  // Ensure panning/sliding never exposes black borders
  const safeMinScale = (panX !== 0 || panY !== 0 || slideOffset !== 0) ? 1.06 : 1.0;
  const finalScale = Math.max(safeMinScale, baseScale * transZoomBurst);

  const showPill = creativeMode !== 'classic_dna' && Boolean(clip.featurePill);
  const pillSpring = showPill
    ? spring({ frame, fps, config: { damping: 13, stiffness: 210, mass: 0.68 } })
    : 0;
  const pillFadeOut = showPill
    ? interpolate(frame, [Math.max(0, totalFrames - 7), totalFrames], [1, 0], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      })
    : 0;
  const pillAlignLeft = clipIdx % 2 === 0;
  const isChecklist = creativeMode === 'flash_checklist';

  const colorCss =
    colorPreset === 'warm_film'
      ? 'sepia(0.10) saturate(1.12) contrast(1.04) brightness(1.02)'
      : colorPreset === 'cool_vivid'
      ? 'saturate(1.16) contrast(1.06) hue-rotate(-5deg) brightness(1.02)'
      : 'none';

  const isCardBlur = layoutStyle === 'card_blur';
  const isTopBanner = layoutStyle === 'top_banner';

  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: '#09090B' }}>
      {isCardBlur ? (
        <OffthreadVideo
          src={staticFile(clip.src)}
          muted
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter: 'blur(24px) brightness(0.42) saturate(1.15)',
            transform: 'scale(1.14)',
          }}
        />
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: isCardBlur ? '6%' : 0,
          right: isCardBlur ? '6%' : 0,
          top: isCardBlur ? '12%' : isTopBanner ? '18%' : 0,
          bottom: isCardBlur ? '13%' : 0,
          overflow: 'hidden',
          borderRadius: isCardBlur ? 36 : 0,
          border: isCardBlur ? '3px solid rgba(255,255,255,0.28)' : 'none',
          boxShadow: isCardBlur ? '0 24px 64px rgba(0,0,0,0.72)' : 'none',
        }}
      >
        <OffthreadVideo
          src={staticFile(clip.src)}
          muted
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter: colorCss,
            transform: `translate(${slideOffset + panX}px, ${panY}px) scale(${finalScale})`,
          }}
        />
      </div>
      {flashOpacity > 0.01 ? (
        <AbsoluteFill style={{ backgroundColor: '#FFFFFF', opacity: flashOpacity }} />
      ) : null}
      {showPill && clip.featurePill ? (
        <div
          style={{
            position: 'absolute',
            top: '57%',
            left: pillAlignLeft ? 52 : undefined,
            right: pillAlignLeft ? undefined : 92,
            transform: `translateY(${interpolate(pillSpring, [0, 1], [16, 0])}px) scale(${interpolate(pillSpring, [0, 1], [0.8, 1])})`,
            opacity: pillFadeOut,
            background: isChecklist
              ? 'linear-gradient(135deg, rgba(15,23,42,0.92), rgba(120,53,15,0.92))'
              : theme.pillBg,
            border: isChecklist ? '2px solid rgba(251,191,36,0.9)' : theme.pillBorder,
            borderRadius: 999,
            padding: '10px 22px',
            boxShadow: '0 8px 22px rgba(0,0,0,0.45)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            zIndex: 25,
            pointerEvents: 'none',
          }}
        >
          <span
            style={{
              fontFamily: `"${fontHeading}", "Montserrat Black", sans-serif`,
              fontWeight: 800,
              fontSize: 30,
              color: isChecklist ? '#FDE68A' : theme.pillText,
              letterSpacing: 0.2,
              textShadow: '0 2px 6px rgba(0,0,0,0.75)',
              whiteSpace: 'nowrap',
            }}
          >
            {isChecklist ? `☑ ${clip.featurePill.replace(/^[^\w\u00C0-\u1EF9]+\s*/, '')}` : clip.featurePill}
          </span>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const TikTokComposition: React.FC<TikTokVideoProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const creativeMode = props.creativeMode || 'breakthrough_ai';
  const cameraIntensity = props.cameraIntensity || 'dynamic_ai';
  const theme = resolveVisualTheme(props.visualTheme);
  const showBreakthrough = !props.badgeOnly && creativeMode !== 'classic_dna';

  const showFloralBadge =
    Boolean(props.floralBadge?.enabled) &&
    (props.badgeStyle === 'floral_badge' || props.badgeStyle === 'floral_plus_callouts');

  const floralEnd = props.floralBadge?.end ?? 4.0;

  // When floral_plus_callouts is active, skip multicolor hook overlapping the floral badge in the first 4s
  const visibleCallouts = props.badgeOnly
    ? []
    : (props.callouts || []).filter((c) => {
        if (props.badgeStyle === 'floral_badge') {
          return false;
        }
        if (props.badgeStyle === 'floral_plus_callouts' && showFloralBadge && c.start < floralEnd - 0.3 && (c.y ?? props.hookY) < 0.4) {
          return false;
        }
        return true;
      });

  const progressPct = Math.min(100, Math.max(0, (frame / Math.max(1, durationInFrames - 1)) * 100));
  const ctaWinStart = Math.max(4.0, (props.durationSec || durationInFrames / fps) - 3.6);
  const currentSec = frame / fps;
  const showCartPointer = showBreakthrough && currentSec >= ctaWinStart && (props.durationSec || 25) > 5.0;
  const cartBounce = showCartPointer ? Math.abs(Math.sin((currentSec - ctaWinStart) * 5.2)) * -10 : 0;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: props.transparentBg ? 'transparent' : '#000000',
      }}
    >
      {/* Video Track */}
      {!props.badgeOnly &&
        (props.clips || []).map((clip, clipIdx) => {
          const from = Math.round(clip.startInTimeline * fps);
          const dur = Math.max(10, Math.round(clip.duration * fps));
          return (
            <Sequence key={clip.id} from={from} durationInFrames={dur}>
              <ClipLayer
                clip={clip}
                clipIdx={clipIdx}
                cameraIntensity={cameraIntensity}
                creativeMode={creativeMode}
                layoutStyle={props.layoutStyle || 'full'}
                colorPreset={props.colorPreset || 'natural'}
                disableFlashShake={props.disableFlashShake !== false}
                fontHeading={props.fontHeading || 'Baloo 2'}
                theme={theme}
              />
            </Sequence>
          );
        })}

      {!props.badgeOnly && props.layoutStyle === 'top_banner' ? (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '18%',
            background: theme.cardBg || 'linear-gradient(180deg, rgba(15,23,42,0.98) 0%, rgba(24,24,27,0.92) 100%)',
            borderBottom: `3px solid ${theme.accentStroke || '#FACC15'}`,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '28px 56px 12px',
            zIndex: 22,
            pointerEvents: 'none',
          }}
        >
          <span
            style={{
              fontFamily: `"${props.fontBrand || 'Montserrat Black'}", "Baloo 2", sans-serif`,
              fontWeight: 900,
              fontSize: 38,
              color: theme.brandColor || '#FFFFFF',
              textTransform: 'uppercase',
              letterSpacing: 1,
              textAlign: 'center',
            }}
          >
            {props.floralBadge?.brand || props.title || 'TIKTOK SHOP REVIEW'}
          </span>
          <span
            style={{
              fontFamily: `"${props.fontHeading || 'Baloo 2'}", sans-serif`,
              fontWeight: 700,
              fontSize: 26,
              color: theme.productColor || '#FFE500',
              marginTop: 4,
              textAlign: 'center',
            }}
          >
            {props.floralBadge?.productLine || props.selectedScriptLabel || 'Review Chân Thực · Săn Deal Hời'}
          </span>
        </div>
      ) : null}

      {/* Audio Tracks */}
      {!props.badgeOnly && props.voiceSrc ? (
        <Audio src={staticFile(props.voiceSrc)} volume={1.0} />
      ) : null}

      {!props.badgeOnly && props.bgmSrc ? (
        <Audio
          src={staticFile(props.bgmSrc)}
          loop
          volume={(f) => {
            const baseVol = props.bgmVolume ?? 0.24;
            const fadeIn = interpolate(f, [0, 12], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
            const fadeOut = interpolate(
              f,
              [Math.max(0, durationInFrames - 20), durationInFrames],
              [1, 0],
              { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
            );
            const tSec = f / fps;
            const wList = props.words || [];
            const isSpeechWindow =
              wList.length > 0 &&
              tSec >= wList[0].start - 0.15 &&
              tSec <= wList[wList.length - 1].end + 0.25;
            const duckMult = isSpeechWindow ? 0.78 : 1.05;
            return Math.min(0.65, baseVol * duckMult * fadeIn * fadeOut);
          }}
        />
      ) : null}

      {!props.badgeOnly &&
        (props.sfxEvents || []).map((sfx) => {
          const from = Math.max(0, Math.round(sfx.start * fps));
          const dur = Math.max(15, Math.round((sfx.duration || 1.2) * fps));
          return (
            <Sequence key={sfx.id} from={from} durationInFrames={dur}>
              <Audio src={staticFile(sfx.src)} volume={sfx.volume ?? props.sfxVolume ?? 0.55} />
            </Sequence>
          );
        })}

      {/* Graphic Overlays */}
      {showFloralBadge ? (
        <FloralHookBadge
          config={props.floralBadge}
          hookY={props.hookY}
          fontBrand={props.fontBrand || 'Montserrat Black'}
          fontScript={props.fontScript || 'Dancing Script'}
          centered={Boolean(props.badgeOnly)}
          visualTheme={theme.id}
        />
      ) : null}

      {visibleCallouts.map((c) => (
        <MulticolorCallout
          key={c.id}
          item={c}
          defaultY={props.hookY}
          fontHeading={props.fontHeading || 'Baloo 2'}
        />
      ))}

      {/* Spoken Karaoke Subtitles (Y = 72% Safe Zone) */}
      {!props.badgeOnly && props.words && props.words.length > 0 ? (
        <KaraokeSubtitles
          words={props.words}
          subtitleY={props.subtitleY || 0.72}
          activeColor={props.subtitleActiveColor || '#FFE500'}
          fontHeading={props.fontHeading || 'Baloo 2'}
        />
      ) : null}

      {/* Breakthrough Overlays: Top Retention Bar + Cart Anchor Pointer */}
      {showBreakthrough ? (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 8,
            backgroundColor: 'rgba(0,0,0,0.35)',
            zIndex: 45,
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${progressPct}%`,
              background: theme.progressGradient,
              boxShadow: '0 0 12px rgba(255,229,0,0.55)',
            }}
          />
        </div>
      ) : null}

      {props.stickerDensity !== 'off' ? (() => {
        const stkStems = props.stickerDensity === 'rich'
          ? ['1f525', '2728', '1f680', '1f389', '26a1', '2764_fe0f']
          : ['1f525', '2728', '1f389', '2764_fe0f'];
        const segDurF = Math.max(45, Math.floor(durationInFrames / stkStems.length));
        return stkStems.map((st, sIdx) => {
          const stF = sIdx * segDurF + 10;
          const durF = Math.min(84, Math.max(30, segDurF - 14));
          if (stF >= durationInFrames - 18) return null;
          const isRight = sIdx % 2 === 0;
          return (
            <Sequence key={`stk-${sIdx}`} from={stF} durationInFrames={durF}>
              <div
                style={{
                  position: 'absolute',
                  top: '14%',
                  right: isRight ? 36 : undefined,
                  left: isRight ? undefined : 36,
                  zIndex: 44,
                  pointerEvents: 'none',
                  filter: 'drop-shadow(0 8px 18px rgba(0,0,0,0.45))',
                }}
              >
                <SharedLottieSticker stem={resolveLottieStem(undefined, st) === '2728' ? st : st} size={126} startFrame={0} />
              </div>
            </Sequence>
          );
        });
      })() : null}

      {showCartPointer ? (
        <div
          style={{
            position: 'absolute',
            bottom: '11.5%',
            left: 52,
            transform: `translateY(${cartBounce}px)`,
            background: theme.ctaBg,
            border: theme.ctaBorder,
            borderRadius: 999,
            padding: '10px 22px',
            boxShadow: '0 10px 26px rgba(0,0,0,0.55)',
            zIndex: 42,
            pointerEvents: 'none',
          }}
        >
          <span
            style={{
              fontFamily: `"${props.fontHeading || 'Baloo 2'}", "Montserrat Black", sans-serif`,
              fontWeight: 800,
              fontSize: 28,
              color: '#FFFFFF',
              textShadow: '0 2px 4px rgba(0,0,0,0.65)',
              whiteSpace: 'nowrap',
            }}
          >
            🛒 Chốt Đơn Giỏ Hàng Góc Trái 👇
          </span>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
