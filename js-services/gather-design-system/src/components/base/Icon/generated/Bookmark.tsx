import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgBookmark = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path fillRule="evenodd" clipRule="evenodd" d="M7.69995 3H16.3C17.405 3 18.3 3.895 18.3 5V21L12.008 17.727L5.69995 21V5C5.69995 3.895 6.59495 3 7.69995 3Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgBookmark);
export default Memo;