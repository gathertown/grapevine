import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgDrawer = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M17.25 19.25C18.3546 19.25 19.25 18.3546 19.25 17.25V4.75C19.25 3.64543 18.3546 2.75 17.25 2.75H6.75C5.64543 2.75 4.75 3.64543 4.75 4.75V17.25C4.75 18.3546 5.64543 19.25 6.75 19.25M17.25 19.25H6.75M17.25 19.25V21.25M6.75 19.25V21.25M19 11H5M9.75 7H14.25M9.75 15H14.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgDrawer);
export default Memo;