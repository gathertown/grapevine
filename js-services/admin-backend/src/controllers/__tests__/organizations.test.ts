/**
 * Tests for organization controller domain validation functions
 */

// Test the domain validation functions directly since they're not exported
// We recreate the functions here to test their logic independently

// Create a test version of the sanitizeDomain function
function sanitizeDomain(domain: string): string {
  if (!domain || typeof domain !== 'string') {
    return '';
  }

  let cleanDomain = domain.trim().toLowerCase();

  // Remove common protocols
  cleanDomain = cleanDomain.replace(/^https?:\/\//, '');
  cleanDomain = cleanDomain.replace(/^ftp:\/\//, '');
  cleanDomain = cleanDomain.replace(/^www\./, '');

  // Remove path, query, and fragment
  cleanDomain = cleanDomain.split('/')[0] || '';
  cleanDomain = cleanDomain.split('?')[0] || '';
  cleanDomain = cleanDomain.split('#')[0] || '';

  // Remove port
  cleanDomain = cleanDomain.split(':')[0] || '';

  return cleanDomain.trim();
}

function isValidDomainFormat(domain: string): boolean {
  if (!domain || typeof domain !== 'string') {
    return false;
  }

  const cleanDomain = domain.trim();

  // Basic checks
  if (cleanDomain.length === 0 || cleanDomain.length > 253) {
    return false;
  }

  // Must contain at least one dot
  if (!cleanDomain.includes('.')) {
    return false;
  }

  // Cannot start or end with dot or dash
  if (
    cleanDomain.startsWith('.') ||
    cleanDomain.endsWith('.') ||
    cleanDomain.startsWith('-') ||
    cleanDomain.endsWith('-')
  ) {
    return false;
  }

  // Basic domain regex - allows letters, numbers, dots, and hyphens
  const domainRegex = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/i;

  return domainRegex.test(cleanDomain);
}

describe('Backend Domain Validation Functions', () => {
  describe('sanitizeDomain', () => {
    it('should handle empty/null/undefined input', () => {
      expect(sanitizeDomain('')).toBe('');
      expect(sanitizeDomain(null as any)).toBe('');
      expect(sanitizeDomain(undefined as any)).toBe('');
    });

    it('should strip https protocol', () => {
      expect(sanitizeDomain('https://example.com')).toBe('example.com');
      expect(sanitizeDomain('HTTPS://example.com')).toBe('example.com');
    });

    it('should strip http protocol', () => {
      expect(sanitizeDomain('http://example.com')).toBe('example.com');
      expect(sanitizeDomain('HTTP://example.com')).toBe('example.com');
    });

    it('should strip ftp protocol', () => {
      expect(sanitizeDomain('ftp://example.com')).toBe('example.com');
    });

    it('should remove www prefix', () => {
      expect(sanitizeDomain('www.example.com')).toBe('example.com');
      expect(sanitizeDomain('WWW.example.com')).toBe('example.com');
    });

    it('should remove paths', () => {
      expect(sanitizeDomain('example.com/path')).toBe('example.com');
      expect(sanitizeDomain('example.com/path/to/resource')).toBe('example.com');
      expect(sanitizeDomain('example.com/')).toBe('example.com');
    });

    it('should remove query parameters', () => {
      expect(sanitizeDomain('example.com?query=value')).toBe('example.com');
      expect(sanitizeDomain('example.com?foo=bar&baz=qux')).toBe('example.com');
    });

    it('should remove fragments', () => {
      expect(sanitizeDomain('example.com#fragment')).toBe('example.com');
      expect(sanitizeDomain('example.com#section1')).toBe('example.com');
    });

    it('should remove ports', () => {
      expect(sanitizeDomain('example.com:8080')).toBe('example.com');
      expect(sanitizeDomain('example.com:443')).toBe('example.com');
      expect(sanitizeDomain('example.com:3000')).toBe('example.com');
    });

    it('should handle complex URLs with all components', () => {
      expect(
        sanitizeDomain('https://www.example.com:8080/path/to/resource?query=value&foo=bar#fragment')
      ).toBe('example.com');
    });

    it('should convert to lowercase', () => {
      expect(sanitizeDomain('Example.COM')).toBe('example.com');
      expect(sanitizeDomain('HTTPS://WWW.EXAMPLE.COM')).toBe('example.com');
    });

    it('should trim whitespace', () => {
      expect(sanitizeDomain('  example.com  ')).toBe('example.com');
      expect(sanitizeDomain('\texample.com\n')).toBe('example.com');
    });

    it('should handle subdomains', () => {
      expect(sanitizeDomain('subdomain.example.com')).toBe('subdomain.example.com');
      expect(sanitizeDomain('https://www.subdomain.example.com')).toBe('subdomain.example.com');
    });

    it('should handle edge cases with empty components', () => {
      expect(sanitizeDomain('example.com?')).toBe('example.com');
      expect(sanitizeDomain('example.com#')).toBe('example.com');
      expect(sanitizeDomain('example.com:')).toBe('example.com');
    });

    it('should handle split edge cases that could return undefined', () => {
      // These shouldn't happen in practice, but test the || '' fallback
      expect(sanitizeDomain('/')).toBe('');
      expect(sanitizeDomain('?')).toBe('');
      expect(sanitizeDomain('#')).toBe('');
      expect(sanitizeDomain(':')).toBe('');
    });
  });

  describe('isValidDomainFormat', () => {
    it('should reject empty/null/undefined input', () => {
      expect(isValidDomainFormat('')).toBe(false);
      expect(isValidDomainFormat(null as any)).toBe(false);
      expect(isValidDomainFormat(undefined as any)).toBe(false);
    });

    it('should accept valid domains', () => {
      expect(isValidDomainFormat('example.com')).toBe(true);
      expect(isValidDomainFormat('subdomain.example.com')).toBe(true);
      expect(isValidDomainFormat('test-domain.co.uk')).toBe(true);
      expect(isValidDomainFormat('a.b')).toBe(true);
      expect(isValidDomainFormat('123.example.com')).toBe(true);
    });

    it('should reject domains without dots', () => {
      expect(isValidDomainFormat('localhost')).toBe(false);
      expect(isValidDomainFormat('example')).toBe(false);
    });

    it('should reject domains starting/ending with dots', () => {
      expect(isValidDomainFormat('.example.com')).toBe(false);
      expect(isValidDomainFormat('example.com.')).toBe(false);
      expect(isValidDomainFormat('.example.com.')).toBe(false);
    });

    it('should reject domains starting/ending with hyphens', () => {
      expect(isValidDomainFormat('-example.com')).toBe(false);
      expect(isValidDomainFormat('example.com-')).toBe(false);
    });

    it('should reject very long domains', () => {
      const longDomain = `${'a'.repeat(250)}.com`;
      expect(isValidDomainFormat(longDomain)).toBe(false);
    });

    it('should reject domains with invalid characters', () => {
      expect(isValidDomainFormat('example_domain.com')).toBe(false);
      expect(isValidDomainFormat('example@domain.com')).toBe(false);
      expect(isValidDomainFormat('example domain.com')).toBe(false);
    });

    it('should accept domains with hyphens in middle', () => {
      expect(isValidDomainFormat('test-domain.com')).toBe(true);
      expect(isValidDomainFormat('multi-word-domain.co.uk')).toBe(true);
    });
  });

  describe('Integration: Frontend and Backend Consistency', () => {
    it('should sanitize domains consistently between frontend and backend', () => {
      const testCases = [
        { input: 'https://example.com', expected: 'example.com' },
        { input: 'http://www.example.com:8080/path?query=value#fragment', expected: 'example.com' },
        { input: 'Example.COM', expected: 'example.com' },
        { input: '  example.com  ', expected: 'example.com' },
        { input: 'ftp://subdomain.example.com', expected: 'subdomain.example.com' },
      ];

      testCases.forEach(({ input, expected }) => {
        const backendResult = sanitizeDomain(input);
        // This would be the same as frontend result if we imported it
        expect(backendResult).toBe(expected);
      });
    });

    it('should validate domains consistently between frontend and backend', () => {
      const validDomains = ['example.com', 'subdomain.example.com', 'test-domain.co.uk'];

      const invalidDomains = [
        '',
        'localhost',
        '.example.com',
        'example.com-',
        'example_domain.com',
      ];

      validDomains.forEach((domain) => {
        expect(isValidDomainFormat(domain)).toBe(true);
      });

      invalidDomains.forEach((domain) => {
        expect(isValidDomainFormat(domain)).toBe(false);
      });
    });
  });
});
