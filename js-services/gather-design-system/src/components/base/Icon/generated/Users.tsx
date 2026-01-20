import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUsers = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M2 19C2 16.791 3.791 15 6 15H10C12.209 15 14 16.791 14 19M16 14H19C20.657 14 22 15.343 22 17M10.4749 6.02513C11.8417 7.39197 11.8417 9.60804 10.4749 10.9749C9.10806 12.3417 6.89199 12.3417 5.52515 10.9749C4.15831 9.60804 4.15831 7.39197 5.52515 6.02513C6.89199 4.65829 9.10806 4.65829 10.4749 6.02513ZM19.2678 6.73223C20.2441 7.70854 20.2441 9.29145 19.2678 10.2678C18.2915 11.2441 16.7086 11.2441 15.7323 10.2678C14.756 9.29145 14.756 7.70854 15.7323 6.73223C16.7086 5.75592 18.2915 5.75592 19.2678 6.73223Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUsers);
export default Memo;