import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSearch = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M21 21L16.5562 16.5562M18.8828 10.9414C18.8828 15.3273 15.3273 18.8828 10.9414 18.8828C6.55547 18.8828 3 15.3273 3 10.9414C3 6.55547 6.55547 3 10.9414 3C15.3273 3 18.8828 6.55547 18.8828 10.9414Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgSearch);
export default Memo;