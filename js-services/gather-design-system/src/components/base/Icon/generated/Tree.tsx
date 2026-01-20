import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgTree = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 21.25V15M12 15L9.75 12.75M12 15L15.25 11.75M20.25 11C20.25 15.5563 16.5563 19.25 12 19.25C7.44365 19.25 3.75 15.5563 3.75 11C3.75 6.44365 7.44365 2.75 12 2.75C16.5563 2.75 20.25 6.44365 20.25 11Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgTree);
export default Memo;