"""Recognise a top-level SC sound Function without executing its .play message.

This is a delimiter/token scan, not a SuperCollider parser. sclang still parses
and compiles the expression. Strings, symbols, characters and nested comments
are skipped so a .play inside text cannot be mistaken for a playback request.
"""


def tokens(source):
    result, i = [], 0
    while i < len(source):
        c = source[i]
        if c.isspace():
            i += 1
        elif source.startswith('//', i):
            end = source.find('\n', i + 2)
            i = len(source) if end < 0 else end + 1
        elif source.startswith('/*', i):
            depth = 1; i += 2
            while i < len(source) and depth:
                if source.startswith('/*', i): depth += 1; i += 2
                elif source.startswith('*/', i): depth -= 1; i += 2
                else: i += 1
        elif c in ('"', "'"):
            start = i; i += 1
            while i < len(source):
                if source[i] == '\\': i += 2
                elif source[i] == c: i += 1; break
                else: i += 1
            result.append(('literal', start, i))
        elif c == '$':
            start = i; i += 2
            if i <= len(source) and source[i - 1] == '\\': i += 1
            result.append(('literal', start, i))
        elif c == '\\' or c.isalpha() or c == '_':
            start = i; i += 1
            while i < len(source) and (source[i].isalnum() or source[i] == '_'): i += 1
            result.append((source[start:i], start, i))
        else:
            result.append((c, i, i + 1)); i += 1
    return result


def matching(items, start):
    pairs = {'(': ')', '[': ']', '{': '}'}
    stack = []
    for i in range(start, len(items)):
        text = items[i][0]
        if text in pairs: stack.append(pairs[text])
        elif text in (')', ']', '}'):
            if not stack or stack.pop() != text: return None
            if not stack: return i
    return None


def expression(source):
    items = tokens(source)
    while items and items[-1][0] == ';': items.pop()
    # Unwrap selection parentheses, including ({ ... }).play and nested forms.
    while items and items[0][0] == '(':
        end = matching(items, 0)
        if end == len(items) - 1:
            items = items[1:-1]
            while items and items[-1][0] == ';': items.pop()
        elif end is not None and [x[0] for x in items[end+1:]] in (['.', 'play'], ['.', 'play', '(', ')']):
            items = items[1:end] + items[end+1:]
        else:
            break
    if items and items[0][0] == '{':
        end = matching(items, 0)
        if end is None or [x[0] for x in items[end+1:]] not in ([], ['.', 'play'], ['.', 'play', '(', ')']):
            raise ValueError('Use one sound block, optionally followed by .play or .play(); playback arguments and extra statements are not supported')
        body = items[:end+1]
        if any(a[0] == '.' and b[0] == 'play' for a, b in zip(body, body[1:])):
            raise ValueError('Nested .play is not supported; return the sound signal from the block')
        return 'sound_block', source[items[0][1]:items[end][2]]
    if any(a[0] == '.' and b[0] == 'play' for a, b in zip(items, items[1:])):
        raise ValueError('Only a top-level sound block may use .play during compilation; return a SynthDef or { sound } block')
    return 'synthdef', source
