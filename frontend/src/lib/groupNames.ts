export const GROUP_RU: Record<string, string> = {
  "uik1-52b": "ИУК1-52Б",
  "uik2-11b": "ИУК2-11Б",
  "uik2-12b": "ИУК2-12Б",
  "uik2-13b": "ИУК2-13Б",
  "uik2-32b": "ИУК2-32Б",
  "uik2-51b": "ИУК2-51Б",
  "uik2-52b": "ИУК2-52Б",
  "uik2-53b": "ИУК2-53Б",
  "uik4-51b": "ИУК4-51Б",
  "uik4-52b": "ИУК4-52Б",
  "uik4-53b": "ИУК4-53Б",
  "uik6-33b": "ИУК6-33Б",
  "mk2-32b": "МК2-32Б",
  "mk3-51b": "МК3-51Б",
};
export const toRu = (en: string) => GROUP_RU[en] ?? en;
