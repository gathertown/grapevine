import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgShareAlt = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M11 14.329C15.594 14.329 19.499 16.692 21 20V18.993C21 12.977 16.579 8.07 11 7.702V3L3 11L11 19V14.333" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgShareAlt);
export default Memo;