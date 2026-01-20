import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowUndo = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8 5L5 8M5 8L8 11M5 8H14C17.314 8 20 10.462 20 13.5C20 16.538 17.314 19 14 19H6" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowUndo);
export default Memo;