import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgVideoStack = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M6 6H18M8 3H16M11.259 13.071L13.976 14.678C14.32 14.881 14.32 15.379 13.976 15.582L11.259 17.189C10.909 17.396 10.467 17.144 10.467 16.737V13.524C10.466 13.116 10.909 12.864 11.259 13.071ZM19 21H5C3.895 21 3 20.105 3 19V11C3 9.895 3.895 9 5 9H19C20.105 9 21 9.895 21 11V19C21 20.105 20.105 21 19 21Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgVideoStack);
export default Memo;