import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowRedo = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M16 5L19 8M19 8L16 11M19 8H10C6.686 8 4 10.462 4 13.5C4 16.538 6.686 19 10 19H18" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowRedo);
export default Memo;