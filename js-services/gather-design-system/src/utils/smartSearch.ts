const DIACRITIC_SPECIAL_CASES: Record<string, string> = {
  Ł: 'L',
  ł: 'l',
  Ø: 'O',
  ø: 'o',
  Đ: 'D',
  đ: 'd',
  Ð: 'D',
  ð: 'd',
  ß: 'ss',
  Æ: 'AE',
  æ: 'ae',
  Œ: 'OE',
  œ: 'oe',
  Ŋ: 'NG',
  ŋ: 'ng',
  Þ: 'Th',
  þ: 'th',
};

const SPECIAL_CHARS_PATTERN = new RegExp(`[${Object.keys(DIACRITIC_SPECIAL_CASES)}]`, 'g');

function removeDiacritics(str: string): string {
  if (!str) return str;
  return str
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .replace(SPECIAL_CHARS_PATTERN, (char) => DIACRITIC_SPECIAL_CASES[char] ?? char);
}

function normalizeString(str: string): string {
  if (!str) return str;
  return removeDiacritics(str).toLowerCase().trim();
}

type SearchOptions = {
  title: string;
  minCharactersToMatch?: number;
  keywords?: string[];
  checkContainsOnTitle?: boolean;
  checkContainsOnKeywords?: boolean;
  enableMultiTermSearch?: boolean;
};

export class SmartStringSearchUtil {
  public static searchCollection<TCollectionType>(
    query: string,
    collection: Iterable<TCollectionType>,
    getOptions: (item: TCollectionType) => SearchOptions
  ): TCollectionType[] {
    return Array.from(collection)
      .map((item) => {
        const options = getOptions(item);
        return [SmartStringSearchUtil.rankMatch(query, options), options, item] as const;
      })
      .filter((entry): entry is [number, SearchOptions, TCollectionType] => entry[0] !== null)
      .toSorted((a, b) => (a[0] === b[0] ? a[1].title.localeCompare(b[1].title) : b[0] - a[0]))
      .map(([_rank, _options, item]) => item);
  }

  public static isMatch(
    query: string,
    {
      title,
      minCharactersToMatch = 1,
      keywords = [],
      checkContainsOnTitle = true,
      checkContainsOnKeywords = false,
      enableMultiTermSearch = false,
    }: SearchOptions
  ): boolean {
    return (
      SmartStringSearchUtil.rankMatch(query, {
        title,
        minCharactersToMatch,
        keywords,
        checkContainsOnTitle,
        checkContainsOnKeywords,
        enableMultiTermSearch,
      }) !== null
    );
  }

  public static rankMatch(
    query: string,
    {
      title,
      minCharactersToMatch = 1,
      keywords = [],
      checkContainsOnTitle = true,
      checkContainsOnKeywords = false,
      enableMultiTermSearch = false,
    }: SearchOptions
  ): number | null {
    const normalizedQuery = normalizeString(query);

    if (normalizedQuery.length < minCharactersToMatch) return null;

    if (enableMultiTermSearch) {
      const terms = normalizedQuery.split(/[,\s]+/).filter(Boolean);
      if (terms.length > 1) {
        const ranks = terms.map((term) =>
          SmartStringSearchUtil.rankSingleTerm(term, {
            title,
            minCharactersToMatch,
            keywords,
            checkContainsOnTitle,
            checkContainsOnKeywords,
          })
        );

        if (ranks.some((rank) => rank === null)) return null;

        const validRanks = ranks.filter((rank): rank is number => rank !== null);
        return Math.min(...validRanks);
      } else if (terms.length === 1 && terms[0]) {
        return SmartStringSearchUtil.rankSingleTerm(terms[0], {
          title,
          minCharactersToMatch,
          keywords,
          checkContainsOnTitle,
          checkContainsOnKeywords,
        });
      }
    }

    return SmartStringSearchUtil.rankSingleTerm(normalizedQuery, {
      title,
      minCharactersToMatch,
      keywords,
      checkContainsOnTitle,
      checkContainsOnKeywords,
    });
  }

  private static rankSingleTerm(
    normalizedQuery: string,
    {
      title,
      minCharactersToMatch = 1,
      keywords = [],
      checkContainsOnTitle = true,
      checkContainsOnKeywords = false,
    }: Omit<SearchOptions, 'enableMultiTermSearch'>
  ): number | null {
    if (normalizedQuery.length < minCharactersToMatch) return null;

    const normalizedTitle = normalizeString(title);

    if (normalizedTitle === normalizedQuery) return 6;
    if (normalizedTitle.startsWith(normalizedQuery)) return 5;

    const normalizedKeywords = keywords.map(normalizeString);

    if (checkContainsOnTitle && normalizedTitle.includes(normalizedQuery)) return 4;
    if (normalizedKeywords.includes(normalizedQuery)) return 3;
    if (normalizedKeywords.some((keyword) => keyword.startsWith(normalizedQuery))) return 2;

    if (
      checkContainsOnKeywords &&
      normalizedKeywords.some((keyword) => keyword.includes(normalizedQuery))
    ) {
      return 1;
    }

    return null;
  }
}
