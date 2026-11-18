import { continueRender, delayRender, staticFile } from 'remotion';

let loaded = false;

export const loadProjectFonts = (): void => {
  if (loaded || typeof window === 'undefined' || typeof FontFace === 'undefined') {
    return;
  }
  loaded = true;
  const handle = delayRender('Loading Vietnamese Google Fonts');

  const specs: Array<{ family: string; file: string; weight: string }> = [
    { family: 'Montserrat Black', file: 'assets/fonts/Montserrat-Black.ttf', weight: '900' },
    { family: 'Baloo 2', file: 'assets/fonts/Baloo2-ExtraBold.ttf', weight: '800' },
    { family: 'Dancing Script', file: 'assets/fonts/DancingScript-Bold.ttf', weight: '700' },
    { family: 'Pacifico', file: 'assets/fonts/Pacifico-Regular.ttf', weight: '400' },
    { family: 'Be Vietnam Pro', file: 'assets/fonts/BeVietnamPro-Black.ttf', weight: '900' },
    { family: 'Anton', file: 'assets/fonts/Anton-Regular.ttf', weight: '400' },
    { family: 'Oswald', file: 'assets/fonts/Oswald-Bold.ttf', weight: '700' },
    { family: 'Nunito', file: 'assets/fonts/Nunito-Black.ttf', weight: '900' },
    { family: 'Quicksand', file: 'assets/fonts/Quicksand-Bold.ttf', weight: '700' },
    { family: 'Bricolage Grotesque', file: 'assets/fonts/BricolageGrotesque-ExtraBold.ttf', weight: '800' },
    { family: 'Lora', file: 'assets/fonts/Lora-Bold.ttf', weight: '700' },
    { family: 'Paytone One', file: 'assets/fonts/PaytoneOne-Regular.ttf', weight: '400' },
  ];

  Promise.all(
    specs.map(async (s) => {
      try {
        const face = new FontFace(s.family, `url(${staticFile(s.file)})`, {
          weight: s.weight,
          style: 'normal',
        });
        const loadedFace = await face.load();
        document.fonts.add(loadedFace);
      } catch (err) {
        console.warn(`Font load failed for ${s.family}:`, err);
      }
    })
  ).finally(() => {
    continueRender(handle);
  });
};
