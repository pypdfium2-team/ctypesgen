## Developer Notes on Code Design

#### Newline Guidelines for the Python Printer

- Use \n only as separator between two known present strings.
- The general guideline is to use leading \n associated to the item that needs the padding.
- Blocks written by sub-methods should have neither leading nor trailing \n.
  Instead, it is most flexible to leave the connection work to the printer's root method.
- The file as a whole shall have exactly one trailing \n, and no leading \n.

Note a few special cases:
- You may "forward-declare" a trailing \n ahead of a known present block that does not have a leading \n, i.e. the trailing \n acts as separator in accordance with the rule above. This is the case e.g. with srcinfo().
- Where newlines depend on a local conditional, they may be handled by the sub-method if tied to a specific place in the control flow. This is the case with print_library(), which only writes to the main file if embed_templates is True, and does not need a separator otherwise.
- The body of Paragraph Contexts may end with a newline for a padding before the End marker. Note that this is not against the rule, because the resulting paragraph (with markers) will _not_ end with \n.
