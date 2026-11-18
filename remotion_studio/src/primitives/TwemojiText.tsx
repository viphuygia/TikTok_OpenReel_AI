import React from 'react';
import { Img, staticFile } from 'remotion';

const KNOWN_TWEMOJI_HEX = new Set([
  '1f525', '2728', '26a1', '2744', '1f4a7', '1f33f', '1f343', '1f353', '1f34b',
  '1f351', '1f347', '1f349', '1f34e', '1f9f4', '1f6e1', '1f48e', '1f381', '1f6d2',
  '1f447', '1f446', '1f449', '1f4af', '1f3af', '1f50b', '1f60b', '1f60d', '1f929',
  '1f973', '1f4a5', '1f31f', '1f4ab', '1f389', '1f38a', '1f3f7', '1f4b8', '1f4b0',
  '1f6cd', '1f4e6', '1f680', '1f451', '1f496', '1faf6', '1f44d', '1f44c', '2705',
  '1fae7', '1f9ca', '1f338',
]);

export function emojiToTwemojiHex(emoji: string): string {
  const cps: string[] = [];
  for (const ch of emoji) {
    const cp = ch.codePointAt(0);
    if (cp && cp !== 0xfe0f) {
      cps.push(cp.toString(16));
    }
  }
  return cps.join('-');
}

export const TwemojiIcon: React.FC<{ emoji: string; size?: number }> = ({ emoji, size = 42 }) => {
  const hx = emojiToTwemojiHex(emoji);
  if (!hx || !KNOWN_TWEMOJI_HEX.has(hx)) {
    return <span style={{ fontSize: size, lineHeight: 1 }}>{emoji}</span>;
  }
  return (
    <Img
      src={staticFile(`assets/emojis/${hx}.svg`)}
      style={{ width: size, height: size, display: 'inline-block', verticalAlign: 'middle' }}
    />
  );
};

const EMOJI_SPLIT_RE = /([\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]\uFE0F?)/gu;

export const TwemojiText: React.FC<{ text: string; iconSize?: number }> = ({ text, iconSize = 30 }) => {
  const parts = String(text || '').split(EMOJI_SPLIT_RE);
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
      {parts.map((part, idx) => {
        if (!part) return null;
        const hx = emojiToTwemojiHex(part);
        if (hx && KNOWN_TWEMOJI_HEX.has(hx)) {
          return (
            <Img
              key={idx}
              src={staticFile(`assets/emojis/${hx}.svg`)}
              style={{ width: iconSize, height: iconSize, display: 'inline-block', verticalAlign: 'middle' }}
            />
          );
        }
        return <span key={idx}>{part}</span>;
      })}
    </span>
  );
};
