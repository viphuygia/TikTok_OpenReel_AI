import React from 'react';
import { Composition } from 'remotion';
import { TikTokComposition } from './TikTokComposition';
import { InnovationComposition } from './templates/innovation/InnovationComposition';
import { TikTokVideoProps } from './types';

const defaultProps: TikTokVideoProps = {
  title: 'TikTok Shop Review',
  durationSec: 25,
  badgeStyle: 'floral_plus_callouts',
  visualTheme: 'auto',
  layoutStyle: 'full',
  colorPreset: 'natural',
  creativeMode: 'breakthrough_ai',
  cameraIntensity: 'dynamic_ai',
  transparentBg: false,
  badgeOnly: false,
  hookY: 0.16,
  subtitleY: 0.72,
  fontHeading: 'Baloo 2',
  fontBrand: 'Montserrat Black',
  fontScript: 'Dancing Script',
  subtitleActiveColor: '#FFE500',
  floralBadge: {
    enabled: true,
    brand: 'Colgate',
    productLine: 'MaxFresh',
    category: 'nước súc miệng',
    brandColor: '#FFFFFF',
    productColor: '#38BDF8',
    categoryColor: '#FFF380',
    accentStrokeColor: '#BE185D',
    outerStrokeColor: '#FFFFFF',
    start: 0,
    end: 4.0,
    y: 0.16,
  },
  callouts: [],
  words: [],
  clips: [],
  bgmVolume: 0.14,
  sfxVolume: 0.55,
  sfxEvents: [],
};

export const RemotionRoot: React.FC = () => {
  const calcMeta = ({ props }: { props: Record<string, unknown> }) => {
    const fps = 30;
    const typed = props as unknown as TikTokVideoProps;
    const durationSec = Math.max(1.5, Number(typed.durationSec) || 25);
    const isLandscape = typed.aspectRatio === '16:9' || (Number(typed.width) > 0 && Number(typed.width) > Number(typed.height || 0));
    const width = Number(typed.width) || (isLandscape ? 1920 : 1080);
    const height = Number(typed.height) || (isLandscape ? 1080 : 1920);
    return {
      durationInFrames: Math.round(durationSec * fps),
      fps,
      width,
      height,
    };
  };

  return (
    <>
      <Composition
        id="TikTokVideo"
        component={TikTokComposition}
        durationInFrames={750}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultProps}
        calculateMetadata={calcMeta}
      />
      <Composition
        id="TikTokInnovation"
        component={InnovationComposition}
        durationInFrames={750}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultProps}
        calculateMetadata={calcMeta}
      />
    </>
  );
};
