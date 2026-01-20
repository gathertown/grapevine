import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgDrink = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M17.9273 11.75L17.3706 20.3788C17.3027 21.4312 16.4293 22.25 15.3747 22.25H8.62498C7.5704 22.25 6.69702 21.4312 6.62913 20.3788L6.07243 11.75M17.9273 11.75L18.1812 7.81438C18.2184 7.23797 17.7609 6.75 17.1833 6.75H6.81645C6.23883 6.75 5.78134 7.23796 5.81852 7.81438L6.07243 11.75M17.9273 11.75H6.07243M11.7499 6.75V4.35434C11.7499 3.41695 12.4009 2.60532 13.316 2.40197L16.2499 1.75" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgDrink);
export default Memo;