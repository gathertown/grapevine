import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserPlusAlt = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M7 20C7 17.544 8.991 15.553 11.447 15.553H16.553C19.009 15.553 21 17.544 21 20M2.5 12H6.5M4.5 14V10M16.9698 5.23015C18.61 6.87035 18.61 9.52964 16.9698 11.1699C15.3296 12.8101 12.6703 12.8101 11.0301 11.1699C9.38991 9.52965 9.38991 6.87036 11.0301 5.23015C12.6703 3.58995 15.3296 3.58995 16.9698 5.23015Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserPlusAlt);
export default Memo;