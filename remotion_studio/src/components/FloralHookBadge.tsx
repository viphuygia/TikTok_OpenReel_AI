import React from 'react';
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { FloralBadgeConfig } from '../types';
import { VisualThemeTokens, resolveVisualTheme } from '../themes';

interface Props {
  config: FloralBadgeConfig;
  hookY: number;
  fontBrand?: string;
  fontScript?: string;
  centered?: boolean;
  visualTheme?: string;
}

const fitMainFontSize = (combinedLen: number): number => {
  if (combinedLen <= 14) return 86;
  if (combinedLen <= 18) return 76;
  if (combinedLen <= 24) return 64;
  return 54;
};

const fitScriptFontSize = (len: number): number => {
  if (len <= 16) return 68;
  if (len <= 24) return 58;
  return 48;
};

export const FloralHookBadge: React.FC<Props> = ({
  config,
  hookY,
  fontBrand = 'Montserrat Black',
  fontScript = 'Dancing Script',
  centered = false,
  visualTheme = 'floral_rose',
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const theme: VisualThemeTokens = resolveVisualTheme(visualTheme);

  const startSec = config.start ?? 0;
  const endSec = config.end ?? 4.0;
  const startFrame = Math.round(startSec * fps);
  const endFrame = Math.round(endSec * fps);

  if (frame < startFrame || frame > endFrame) {
    return null;
  }

  const localFrame = frame - startFrame;
  const totalFrames = Math.max(10, endFrame - startFrame);

  const popIn = spring({
    frame: localFrame,
    fps,
    config: { damping: 11, stiffness: 170, mass: 0.78 },
  });

  const fadeOut = interpolate(
    localFrame,
    [Math.max(0, totalFrames - 10), totalFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const scaleOut = interpolate(
    localFrame,
    [Math.max(0, totalFrames - 10), totalFrames],
    [1, 0.9],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const scale = interpolate(popIn, [0, 1], [0.45, 1]) * scaleOut;
  const twinkle = 0.88 + 0.18 * Math.sin(localFrame * 0.25);
  const floatY = Math.sin(localFrame * 0.14) * 5;

  const brand = (config.brand || '').trim();
  const product = (config.productLine || '').trim();
  const category = (config.category || '').trim();
  const brandColor = theme.brandColor || config.brandColor || '#FFFFFF';
  const productColor = theme.productColor || config.productColor || '#38BDF8';
  const categoryColor = theme.categoryColor || config.categoryColor || '#FFF380';
  const accentStroke = theme.accentStroke || config.accentStrokeColor || '#BE185D';
  const outerStroke = theme.outerStroke || config.outerStrokeColor || '#FFFFFF';

  const combinedText = `${brand} ${product}`.trim();
  const mainSize = fitMainFontSize(combinedText.length);
  const scriptSize = fitScriptFontSize(category.length);

  const renderDoubleStrokedText = (
    text: string,
    fillColor: string,
    fontSize: number,
    fontFamily: string,
    innerColor: string,
    outerColor: string,
    fontWeight: number | string
  ) => (
    <span style={{ position: 'relative', display: 'inline-block', margin: '0 8px' }}>
      {/* Outer white/sticker halo */}
      <span
        aria-hidden
        style={{
          position: 'absolute',
          inset: 0,
          fontFamily: `"${fontFamily}", "Baloo 2", sans-serif`,
          fontWeight,
          fontSize,
          lineHeight: 1.08,
          color: outerColor,
          WebkitTextStroke: `${Math.round(fontSize * 0.26)}px ${outerColor}`,
          paintOrder: 'stroke fill',
          filter: 'drop-shadow(0 8px 16px rgba(0,0,0,0.55))',
          userSelect: 'none',
        }}
      >
        {text}
      </span>
      {/* Inner accent outline */}
      <span
        aria-hidden
        style={{
          position: 'absolute',
          inset: 0,
          fontFamily: `"${fontFamily}", "Baloo 2", sans-serif`,
          fontWeight,
          fontSize,
          lineHeight: 1.08,
          color: innerColor,
          WebkitTextStroke: `${Math.round(fontSize * 0.14)}px ${innerColor}`,
          paintOrder: 'stroke fill',
          userSelect: 'none',
        }}
      >
        {text}
      </span>
      {/* Foreground gradient/solid text */}
      <span
        style={{
          position: 'relative',
          fontFamily: `"${fontFamily}", "Baloo 2", sans-serif`,
          fontWeight,
          fontSize,
          lineHeight: 1.08,
          color: fillColor,
        }}
      >
        {text}
      </span>
    </span>
  );

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: centered ? '50%' : `${(config.y ?? hookY) * 100}%`,
        transform: `translateY(${centered ? '-50%' : '-20%'}) translateY(${floatY}px) scale(${scale})`,
        opacity: fadeOut,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        paddingLeft: 56,
        paddingRight: 56,
        pointerEvents: 'none',
        zIndex: 30,
      }}
    >
      <div
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          maxWidth: 940,
          background: theme.cardBg || 'transparent',
          border: theme.cardBorder || 'none',
          borderRadius: theme.cardBg ? 28 : 0,
          padding: theme.cardBg ? '22px 34px 20px' : 0,
          boxShadow: theme.cardBg ? '0 14px 36px rgba(0,0,0,0.52)' : 'none',
          transform: theme.cardTiltDeg ? `rotate(${theme.cardTiltDeg}deg)` : undefined,
        }}
      >
        {theme.topTag ? (
          <div
            style={{
              marginBottom: 8,
              padding: '6px 18px',
              borderRadius: 999,
              background: theme.topTagBg || '#FACC15',
              color: theme.topTagColor || '#111827',
              fontFamily: `"${fontBrand}", "Baloo 2", sans-serif`,
              fontWeight: 900,
              fontSize: 22,
              letterSpacing: 0.6,
              boxShadow: '0 4px 12px rgba(0,0,0,0.35)',
            }}
          >
            {theme.topTag}
          </div>
        ) : null}

        {/* Top Botanical Floral Ornament (Floral Rose theme) */}
        {theme.showFloral ? (
          <Img
            src={staticFile('assets/stickers/floral_top.svg')}
            style={{
              width: 390,
              height: 105,
              objectFit: 'contain',
              marginBottom: -14,
              filter: 'drop-shadow(0 4px 10px rgba(0,0,0,0.45))',
            }}
          />
        ) : null}

        {/* Sparkle Stars */}
        <Img
          src={staticFile('assets/stickers/sparkle_star.svg')}
          style={{
            position: 'absolute',
            left: -46,
            top: 38,
            width: 58,
            height: 58,
            transform: `scale(${twinkle}) rotate(${localFrame * 1.6}deg)`,
          }}
        />
        <Img
          src={staticFile('assets/stickers/sparkle_star.svg')}
          style={{
            position: 'absolute',
            right: -46,
            bottom: 34,
            width: 50,
            height: 50,
            transform: `scale(${2 - twinkle}) rotate(${-localFrame * 1.4}deg)`,
          }}
        />

        {/* Line 1: Brand + Product Line */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'baseline',
            justifyContent: 'center',
            textAlign: 'center',
          }}
        >
          {brand ? renderDoubleStrokedText(brand, brandColor, mainSize, fontBrand, accentStroke, outerStroke, 900) : null}
          {product ? renderDoubleStrokedText(product, productColor, mainSize, fontBrand, '#0F172A', outerStroke, 900) : null}
        </div>

        {/* Line 2: Category Script Font */}
        {category ? (
          <div style={{ marginTop: 4, textAlign: 'center' }}>
            {renderDoubleStrokedText(
              category,
              categoryColor,
              scriptSize,
              fontScript,
              '#000000',
              accentStroke,
              700
            )}
          </div>
        ) : null}

        {/* Bottom Botanical Floral Ornament (Floral Rose theme) */}
        {theme.showFloral ? (
          <Img
            src={staticFile('assets/stickers/floral_bottom.svg')}
            style={{
              width: 360,
              height: 86,
              objectFit: 'contain',
              marginTop: -6,
              filter: 'drop-shadow(0 4px 10px rgba(0,0,0,0.45))',
            }}
          />
        ) : null}
      </div>
    </div>
  );
};
