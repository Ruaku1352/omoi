const MAX_SIDE = 2048;
const QUALITY = 0.85;

export async function resizeImage(file: File): Promise<File> {
  const bitmap = await createImageBitmap(file);

  let newWidth = bitmap.width;
  let newHeight = bitmap.height;

  const longSide = Math.max(bitmap.width, bitmap.height);
  if (longSide > MAX_SIDE) {
    const ratio = MAX_SIDE / longSide;
    newWidth = Math.round(bitmap.width * ratio);
    newHeight = Math.round(bitmap.height * ratio);
  }

  const canvas = document.createElement('canvas');
  canvas.width = newWidth;
  canvas.height = newHeight;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(bitmap, 0, 0, newWidth, newHeight);

  const blob = await new Promise<Blob>((resolve) => {
    canvas.toBlob((b) => resolve(b!), 'image/jpeg', QUALITY);
  });

  return new File([blob], file.name, { type: 'image/jpeg' });
}