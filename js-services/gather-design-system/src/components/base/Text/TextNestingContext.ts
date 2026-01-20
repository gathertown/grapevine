import React from 'react';

// isNested = false means "we are top-level <Text>"
// isNested = true means "we are inside another <Text>"
export const TextNestingContext = React.createContext<boolean>(false);
