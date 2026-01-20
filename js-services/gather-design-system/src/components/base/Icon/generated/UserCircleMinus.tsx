import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserCircleMinus = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M10 15H7C4.79086 15 3 16.7909 3 19V20M18 17.75H15.5M21 17.75C21 20.0972 19.0972 22 16.75 22C14.4028 22 12.5 20.0972 12.5 17.75C12.5 15.4028 14.4028 13.5 16.75 13.5C19.0972 13.5 21 15.4028 21 17.75ZM15 7C15 9.20914 13.2091 11 11 11C8.79086 11 7 9.20914 7 7C7 4.79086 8.79086 3 11 3C13.2091 3 15 4.79086 15 7Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserCircleMinus);
export default Memo;