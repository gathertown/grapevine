/**
 * Tests for domain validation and sanitization utilities
 */

import { fieldValidators } from '../fieldValidators';

describe('fieldValidators.slackBotName', () => {
  const validator = fieldValidators.slackBotName;

  describe('validate', () => {
    it('should accept valid bot names', () => {
      expect(validator.validate('My Company AI')).toBe(true);
      expect(validator.validate('Bot123')).toBe(true);
      expect(validator.validate('Support Bot Beta')).toBe(true); // removed parentheses
      expect(validator.validate('AI Assistant v2.0')).toBe(true);
      expect(validator.validate('Company-Bot')).toBe(true);
      expect(validator.validate('Bot_Helper')).toBe(true);
    });

    it('should reject empty or whitespace-only names', () => {
      expect(validator.validate('')).toBe(false);
      expect(validator.validate('   ')).toBe(false);
      expect(validator.validate('\t\n')).toBe(false);
    });

    it('should reject names that are too long', () => {
      const longName = 'a'.repeat(36); // 36 chars, over the 35 limit
      expect(validator.validate(longName)).toBe(false);
    });

    it('should accept names at the character limit', () => {
      const exactLimit = 'a'.repeat(35); // exactly 35 chars
      expect(validator.validate(exactLimit)).toBe(true);
    });

    it('should accept names with allowed characters', () => {
      expect(validator.validate('My Bot')).toBe(true); // spaces allowed
      expect(validator.validate('Bot-123')).toBe(true); // hyphens allowed
      expect(validator.validate('AI_Assistant')).toBe(true); // underscores allowed
      expect(validator.validate('Bot v2.0')).toBe(true); // periods allowed
      expect(validator.validate('MyBot123')).toBe(true); // alphanumeric
      expect(validator.validate('Test-Bot_v1.0')).toBe(true); // combination
    });

    it('should reject names with invalid characters', () => {
      expect(validator.validate('Bot & Assistant')).toBe(false); // ampersand not allowed
      expect(validator.validate('AI (v2.0)')).toBe(false); // parentheses not allowed
      expect(validator.validate('Support Bot!')).toBe(false); // exclamation not allowed
      expect(validator.validate('Bot @ Work')).toBe(false); // @ not allowed
      expect(validator.validate('My Bot #1')).toBe(false); // # not allowed
      expect(validator.validate('Bot$Name')).toBe(false); // $ not allowed
      expect(validator.validate('Bot%Test')).toBe(false); // % not allowed
      expect(validator.validate('Bot+Helper')).toBe(false); // + not allowed
      expect(validator.validate('Bot*AI')).toBe(false); // * not allowed
    });
  });

  describe('transform', () => {
    it('should trim whitespace', () => {
      expect(validator.transform?.('  Bot Name  ')).toBe('Bot Name');
      expect(validator.transform?.('\tBot Name\n')).toBe('Bot Name');
    });
  });
});
