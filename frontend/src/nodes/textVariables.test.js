import { extractVariables, isValidVariableName } from './textVariables';

describe('textVariables logic', () => {
  test('isValidVariableName validates correct JS variable names', () => {
    expect(isValidVariableName('myVar')).toBe(true);
    expect(isValidVariableName('a_1')).toBe(true);
    expect(isValidVariableName('$var')).toBe(true);
    
    // Invalid variable names
    expect(isValidVariableName('123var')).toBe(false);
    expect(isValidVariableName('my-var')).toBe(false);
    expect(isValidVariableName('my var')).toBe(false);
    expect(isValidVariableName('true')).toBe(false); // Reserved keyword
    expect(isValidVariableName('class')).toBe(false); // Reserved keyword
  });

  test('extractVariables extracts variables enclosed in double curly brackets', () => {
    const text = 'Hello {{first_name}} and {{last_name}}, your score is {{score}}. Ignore {{ class }} and {{ 123var }} and {{ x - y }}!';
    const vars = extractVariables(text);
    expect(vars).toEqual(['first_name', 'last_name', 'score']);
  });

  test('extractVariables handles empty, null or undefined input', () => {
    expect(extractVariables('')).toEqual([]);
    expect(extractVariables(null)).toEqual([]);
    expect(extractVariables(undefined)).toEqual([]);
  });

  test('extractVariables returns unique variables in order of appearance', () => {
    const text = '{{user}} says {{message}} and then {{user}} again.';
    const vars = extractVariables(text);
    expect(vars).toEqual(['user', 'message']);
  });
});
