// Specific debounce for field validation
export function debounce(
  func: (fieldName: string, value: string) => void,
  delay: number
): (fieldName: string, value: string) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  return (fieldName: string, value: string): void => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }

    timeoutId = setTimeout(() => {
      func(fieldName, value);
      timeoutId = null;
    }, delay);
  };
}
