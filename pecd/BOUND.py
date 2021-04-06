#!/usr/bin/env python3
# -*- coding: utf-8; fill-column: 120 -*-
#
# Copyright (C) 2021 Emil Zak <emil.zak@cfel.de>
#

import input
import MAPPING
import POTENTIAL
import GRID
import constants

import numpy as np
from scipy import sparse
from scipy.special import sph_harm
import quadpy

from sympy.functions.elementary.miscellaneous import sqrt

import sys
import os.path
import time

from numba import jit, prange

import matplotlib.pyplot as plt
from matplotlib import cm, colors

""" start of @jit section """
#@jit(nopython=True, parallel=False, cache = False, fastmath=False) 
def P(l, m, x):
	pmm = np.ones(1,)
	if m>0:
		somx2 = np.sqrt((1.0-x)*(1.0+x))
		fact = 1.0
		for i in range(1,m+1):
			pmm = pmm * (-1.0 * fact) * somx2
			fact = fact + 2.0
	
	if l==m :
		return pmm * np.ones(x.shape,)
	
	pmmp1 = x * (2.0*m+1.0) * pmm
	
	if l==m+1:
		return pmmp1
	
	pll = np.zeros(x.shape)
	for ll in range(m+2, l+1):
		pll = ( (2.0*ll-1.0)*x*pmmp1-(ll+m-1.0)*pmm ) / (ll-m)
		pmm = pmmp1
		pmmp1 = pll
	
	return pll

LOOKUP_TABLE = np.array([
    1, 1, 2, 6, 24, 120, 720, 5040, 40320,
    362880, 3628800, 39916800, 479001600,
    6227020800, 87178291200, 1307674368000,
    20922789888000, 355687428096000, 6402373705728000,
    121645100408832000, 2432902008176640000], dtype='int64')
    
#@jit(nopython=True, parallel=False, cache = False, fastmath=False) 
def fast_factorial(n):
    return LOOKUP_TABLE[n]

def factorial(x):
	if(x == 0):
		return 1.0
	return x * factorial(x-1)

#@jit(nopython=True, parallel=False, cache = False, fastmath=False) 
def K(l, m):
	return np.sqrt( ((2 * l + 1) * fast_factorial(l-m)) / (4*np.pi*fast_factorial(l+m)) )

#@jit(nopython=True, parallel=False, cache = False, fastmath=False) 
def SH(l, m, theta, phi):
	if m==0 :
		return K(l,m)*P(l,m,np.cos(theta))*np.ones(phi.shape,)
	elif m>0 :
		return np.sqrt(2.0)*K(l,m)*np.cos(m*phi)*P(l,m,np.cos(theta))
	else:
		return np.sqrt(2.0)*K(l,-m)*np.sin(-m*phi)*P(l,-m,np.cos(theta))

#@jit( nopython=True, parallel=False, cache = False, fastmath=False) 
def calc_potmat_jit( vlist, VG, Gs ):
    pot = []
    potind = []
    for p1 in prange(vlist.shape[0]):
        #print(vlist[p1,:])
        w = Gs[vlist[p1,0]][:,2]
        G = Gs[vlist[p1,0]] 
        V = VG[vlist[p1,0]]

        f = SH( vlist[p1,1] , vlist[p1,2]  , G[:,0], G[:,1] + np.pi ) * \
            SH( vlist[p1,3] , vlist[p1,4]  , G[:,0], G[:,1] + np.pi ) * \
            V[:]

        pot.append( [np.dot(w,f.T) * 4.0 * np.pi ] )
        potind.append( [ vlist[p1,5], vlist[p1,6] ] )
        #potmat[vlist[p1,5],vlist[p1,6]] = np.dot(w,f.T) * 4.0 * np.pi
    return pot, potind



#@jit( nopython=True, parallel=False, cache = False, fastmath=False) 
def calc_potmatelem_xi( V, Gs, l1, m1, l2, m2 ):
    #calculate matrix elements from sphlist at point xi with V and Gs calculated at a given quadrature grid.
    w = Gs[:,2]
    f = SH( l1 , m1  , Gs[:,0], Gs[:,1] + np.pi ) * \
        SH( l2 , m2  , Gs[:,0], Gs[:,1] + np.pi ) * V[:]
    return np.dot(w,f.T) * 4.0 * np.pi 

""" end of @jit section """


def BUILD_HMAT0(params):

    maparray, Nbas = MAPPING.GENMAP( params['bound_nlobs'], params['bound_nbins'], params['bound_lmax'], \
                                     params['map_type'], params['working_dir'] )

    Gr, Nr = GRID.r_grid( params['bound_nlobs'], params['bound_nbins'], params['bound_binw'],  params['bound_rshift'] )

    if params['hmat_format'] == 'csr':
        hmat = sparse.csr_matrix((Nbas, Nbas), dtype=np.float64)
    elif params['hmat_format'] == 'regular':
        hmat = np.zeros((Nbas, Nbas), dtype=np.float64)

    """ calculate hmat """
    potmat0, potind = BUILD_POTMAT0( params, maparray, Nbas , Gr )
        
    for ielem, elem in enumerate(potmat0):
        #print(potind[ielem][0],potind[ielem][1])
        hmat[ potind[ielem][0],potind[ielem][1] ] = elem[0]

    start_time = time.time()
    keomat0 = BUILD_KEOMAT0( params, maparray, Nbas , Gr )
    end_time = time.time()
    print("Time for construction of KEO matrix is " +  str("%10.3f"%(end_time-start_time)) + "s")

    hmat += keomat0 

    #plot_mat(hmat)
    #plt.spy(hmat,precision=params['sph_quad_tol'], markersize=5)
    #plt.show()
    
    """ diagonalize hmat """
    start_time = time.time()
    enr0, coeffs0 = np.linalg.eigh(hmat, UPLO = 'U')
    end_time = time.time()
    print("Time for diagonalization of field-free Hamiltonian: " +  str("%10.3f"%(end_time-start_time)) + "s")


    plot_wf_rad(0.0, params['bound_binw'],1000,coeffs0,maparray,Gr,params['bound_nlobs'], params['bound_nbins'])

    print("Normalization of the wavefunction: ")
    for v in range(params['num_ini_vec']):
        print(str(v) + " " + str(np.sqrt( np.sum( np.conj(coeffs0[:,v] ) * coeffs0[:,v] ) )))

    if params['save_ham0'] == True:
        if params['hmat_format'] == 'csr':
            sparse.save_npz( params['working_dir'] + params['file_hmat0'] , hmat , compressed = False )
        elif params['hmat_format'] == 'regular':
            with open( params['working_dir'] + params['file_hmat0'] , 'w') as hmatfile:   
                np.savetxt(hmatfile, hmat, fmt = '%10.4e')

    if params['save_psi0'] == True:
        psi0file = open(params['working_dir'] + params['file_psi0'], 'w')
        for ielem,elem in enumerate(maparray):
            psi0file.write( " %5d"%elem[0] +  " %5d"%elem[1] + "  %5d"%elem[2] + \
                            " %5d"%elem[3] +  " %5d"%elem[4] + "\t" + \
                            "\t\t ".join('{:10.5e}'.format(coeffs0[ielem,v]) for v in range(0,params['num_ini_vec'])) + "\n")

    if params['save_enr0'] == True:
        with open(params['working_dir'] + params['file_enr0'], "w") as energyfile:   
            np.savetxt( energyfile, enr0 * constants.ev_to_au , fmt='%10.5f' )
  


""" ============ KEOMAT0 ============ """
def BUILD_KEOMAT0( params, maparray, Nbas, Gr ):
    nlobs = params['bound_nlobs']
    """call Gauss-Lobatto rule """
    x   =   np.zeros(nlobs)
    w   =   np.zeros(nlobs)
    x,w =   GRID.gauss_lobatto(nlobs,14)
    x   =   np.array(x)
    w   =   np.array(w)

    keomat =  np.zeros((Nbas, Nbas), dtype=np.float64)

    for i in range(Nbas):
        rin = Gr[maparray[i][0],maparray[i][1]]
        for j in range(i,Nbas):
            if maparray[i][3] == maparray[j][3] and maparray[i][4] == maparray[j][4]:
                keomat[i,j] = calc_keomatel(maparray[i][0], maparray[i][1],\
                                            maparray[i][3], maparray[j][0], maparray[j][1], x, w, rin, \
                                            params['bound_rshift'],params['bound_binw'])

    print("KEO matrix")
    with np.printoptions(precision=3, suppress=True, formatter={'float': '{:10.3f}'.format}, linewidth=400):
        print(0.5*keomat)

    #plt.spy(keomat, precision=params['sph_quad_tol'], markersize=5)
    #plt.show()

    return  0.5 * keomat

def calc_keomatel(i1,n1,l1,i2,n2,x,w,rin,rshift,binwidth):
    "calculate matrix element of the KEO"

    if i1==i2 and n1==n2:
        KEO     =  KEO_matel_rad(i1,n1,i2,n2,x,w,rshift,binwidth) + KEO_matel_ang(i1,n1,l1,rin) 
        return     KEO
    else:
        KEO     =  KEO_matel_rad(i1,n1,i2,n2,x,w,rshift,binwidth)
        return     KEO

def KEO_matel_rad(i1,n1,i2,n2,x,w,rshift,binwidth):
    #w /= sqrt(sum(w[:]))
    w_i1     = w#/sum(w[:])
    w_i2     = w#/sum(w[:]) 

    nlobatto = x.size

    if n1>0 and n2>0:
        if i1==i2:
            #single x single
            KEO     =   KEO_matel_fpfp(i1,n1,n2,x,w_i1,rshift,binwidth) #checked
            return      KEO/sqrt(w_i1[n1] * w_i2[n2])
        else:
            return      0.0

    if n1==0 and n2>0:
        #bridge x single
        if i1==i2: 
            KEO     =   KEO_matel_fpfp(i2,nlobatto-1,n2,x,w_i2,rshift,binwidth) # not nlobatto -2?
            return      KEO/sqrt(w_i2[n2]*(w_i1[nlobatto-1]+w_i1[0]))
        elif i1==i2-1:
            KEO     =   KEO_matel_fpfp(i2,0,n2,x,w_i2,rshift,binwidth) # i2 checked  Double checked Feb 12
            return      KEO/sqrt(w_i2[n2]*(w_i1[nlobatto-1]+w_i1[0]))
        else:
            return      0.0

    elif n1>0 and n2==0:
        #single x bridge
        if i1==i2: 
            KEO     =   KEO_matel_fpfp(i1,n1,nlobatto-1,x,w_i1,rshift,binwidth) #check  Double checked Feb 12
            return      KEO/sqrt(w_i1[n1]*(w_i2[nlobatto-1]+w_i2[0]))
        elif i1==i2+1:
            KEO     =   KEO_matel_fpfp(i1,n1,0,x,w_i1,rshift,binwidth) #check  Double checked Feb 12
            return      KEO/sqrt(w_i1[n1]*(w_i2[nlobatto-1]+w_i2[0]))
        else:
            return      0.0
            
    elif n1==0 and n2==0:
        #bridge x bridge
        if i1==i2: 
            KEO     =   ( KEO_matel_fpfp(i1,nlobatto-1,nlobatto-1,x,w_i1,rshift,binwidth) + KEO_matel_fpfp(i1+1,0,0,x,w_i1,rshift,binwidth) ) / sqrt((w_i1[nlobatto-1]+w_i1[0])*(w_i2[nlobatto-1]+w_i2[0])) #checked 10feb 2021   
            return      KEO
        elif i1==i2-1:
            KEO     =   KEO_matel_fpfp(i2,nlobatto-1,0,x,w_i2,rshift,binwidth) #checked 10feb 2021 Double checked Feb 12
            return      KEO/sqrt((w_i1[nlobatto-1]+w_i1[0])*(w_i2[nlobatto-1]+w_i2[0]))
        elif i1==i2+1:
            KEO     =   KEO_matel_fpfp(i1,nlobatto-1,0,x,w_i1,rshift,binwidth) #checked 10feb 2021. Double checked Feb 12
            return      KEO/sqrt((w_i1[nlobatto-1]+w_i1[0])*(w_i2[nlobatto-1]+w_i2[0]))
        else:
            return      0.0

def KEO_matel_ang(i1,n1,l,rgrid):
    """Calculate the anglar momentum part of the KEO"""
    """ we pass full grid and return an array on the full grid. If needed we can calculate only singlne element r_i,n """ 
    #r=0.5e00*(Rbin*x+Rbin*(i+1)+Rbin*i)+epsilon
    return float(l)*(float(l)+1)/((rgrid)**2)

def KEO_matel_fpfp(i,n1,n2,x,w,rshift,binwidth):
    "Calculate int_r_i^r_i+1 f'(r)f'(r) dr in the radial part of the KEO"
    # f'(r) functions from different bins are orthogonal
    #scale the Gauss-Lobatto points
    nlobatto    = x.size
    x_new       = 0.5 * ( binwidth * x + binwidth * (i+1) + binwidth * i + rshift)  #checked
    #scale the G-L quadrature weights
    #w *= 0.5 * binwidth 

    fpfpint=0.0e00
    for k in range(0, nlobatto):
        y1      = fp(i,n1,k,x_new)#*sqrt(w[n1])
        y2      = fp(i,n2,k,x_new)#*sqrt(w[n2])
        fpfpint += w[k] * y1 * y2 #*0.5 * binwidth # 

    return fpfpint#sum(w[:])
    
def fp(i,n,k,x):
    "calculate d/dr f_in(r) at r_ik (Gauss-Lobatto grid) " 
    if n!=k:
        fprime  =   (x[n]-x[k])**(-1)
        prod    =   1.0e00

        for mu in range(0,x.size):
            if mu !=k and mu !=n:
                prod *= (x[k]-x[mu])/(x[n]-x[mu])
        fprime  *=  prod

    elif n==k:
        fprime  =   0.0
        for mu in range(0,x.size):
                if mu !=n:
                    fprime += (x[n]-x[mu])**(-1)
    return fprime

""" ============ POTMAT0 ============ """
def BUILD_POTMAT0( params, maparray, Nbas , Gr ):

    if params['esp_mode'] == "interpolation":
        print("Interpolating electrostatic potential")
        esp_interpolant = POTENTIAL.INTERP_POT(params)

        if  params['gen_adaptive_quads'] == True:
            sph_quad_list = gen_adaptive_quads( params, esp_interpolant, Gr )
        elif params['gen_adaptive_quads'] == False and params['use_adaptive_quads'] == True:
            sph_quad_list = read_adaptive_quads(params)
        elif params['gen_adaptive_quads'] == False and params['use_adaptive_quads'] == False:
            print("using global quadrature scheme")

    elif params['esp_mode'] == "exact":
        if  params['gen_adaptive_quads'] == True:
            sph_quad_list = gen_adaptive_quads_exact( params,  Gr )
        elif params['gen_adaptive_quads'] == False and params['use_adaptive_quads'] == True:
            sph_quad_list = read_adaptive_quads(params)
        elif params['gen_adaptive_quads'] == False and params['use_adaptive_quads'] == False:
            print("using global quadrature scheme")



    start_time = time.time()
    Gs = GRID.GEN_GRID( sph_quad_list )
    end_time = time.time()
    print("Time for grid generation: " +  str("%10.3f"%(end_time-start_time)) + "s")

    if params['esp_mode'] == "interpolate":
        start_time = time.time()
        VG = POTENTIAL.BUILD_ESP_MAT( Gs, Gr, esp_interpolant, params['r_cutoff'] )
        end_time = time.time()
        print("Time for construction of ESP on the grid: " +  str("%10.3f"%(end_time-start_time)) + "s")

    elif params['esp_mode'] == "exact":
        start_time = time.time()
        VG = POTENTIAL.BUILD_ESP_MAT_EXACT(params, Gs, Gr)
        end_time = time.time()
        print("Time for construction of ESP on the grid: " +  str("%10.3f"%(end_time-start_time)) + "s")
        print(VG)

    start_time = time.time()
    vlist = MAPPING.GEN_VLIST( maparray, Nbas, params['map_type'] )
    vlist = np.asarray(vlist)
    end_time = time.time()
    print("Time for construction of vlist: " +  str("%10.3f"%(end_time-start_time)) + "s")
    

    if params['calc_method'] == 'jit':
        start_time = time.time()
        potmat0, potind = calc_potmat_jit( vlist, VG, Gs )
        end_time = time.time()
        print("First call: Time for construction of potential matrix is " +  str("%10.3f"%(end_time-start_time)) + "s")

        #start_time = time.time()
        #potmat0, potind = calc_potmat_jit( vlist, VG, Gs )
        #end_time = time.time()
        #print("Second call: Time for construction of potential matrix is " +  str("%10.3f"%(end_time-start_time)) + "s")
    """
    if params['hmat_format'] == "regular":
        potmat = convert_lists_to_regular(potmat0,potind)
    elif params['hmat_format'] == "csr":
        potmat = convert_lists_to_csr(potmat0,potind)
    """
    return potmat0, potind

def calc_potmatelem_quadpy( l1, m1, l2, m2, rin, scheme, esp_interpolant ):
    """calculate single element of the potential matrix on an interpolated potential"""
    myscheme = quadpy.u3.schemes[scheme]()
    """
    Symbols: 
            theta_phi[0] = theta in [0,pi]
            theta_phi[1] = phi  in [-pi,pi]
            sph_harm(m1, l1,  theta_phi[1]+np.pi, theta_phi[0])) means that we 
                                                                 put the phi angle in range [0,2pi] and 
                                                                 the  theta angle in range [0,pi] as required by 
                                                                 the scipy special funciton sph_harm
    """
    val = myscheme.integrate_spherical(lambda theta_phi: np.conjugate( sph_harm( m1, l1,  theta_phi[1]+np.pi, theta_phi[0] ) ) \
                                                                     * sph_harm( m2, l2, theta_phi[1]+np.pi, theta_phi[0] ) \
                                                                     * POTENTIAL.calc_interp_sph( esp_interpolant, rin, theta_phi[0], theta_phi[1]+np.pi) ) 

    return val

def read_adaptive_quads(params):
    levels = []
    quadfilename = params['working_dir'] + params['file_quad_levels'] 
    fl = open( quadfilename , 'r' )
    for line in fl:
        words   = line.split()
        i       = int(words[0])
        n       = int(words[1])
        xi      = int(words[2])
        scheme  = str(words[3])
        levels.append([i,n,xi,scheme])
    return levels

def gen_adaptive_quads(params, esp_interpolant, rgrid):

    sph_quad_list = [] #list of quadrature levels needed to achieve convergence quad_tol of the potential energy matrix elements (global)

    lmax = params['bound_lmax']
    quad_tol = params['sph_quad_tol']

    print("Testing potential energy matrix elements using Lebedev quadratures")

    sphlist = MAPPING.GEN_SPHLIST(lmax)

    val =  np.zeros( shape = ( len(sphlist)**2 ), dtype=complex)
    val_prev = np.zeros( shape = ( len(sphlist)**2 ), dtype=complex)

    spherical_schemes = []
    for elem in list(quadpy.u3.schemes.keys()):
        if 'lebedev' in elem:
            spherical_schemes.append(elem)

    xi = 0
    for i in range(np.size( rgrid, axis=0 )): 
        for n in range(np.size( rgrid, axis=1 )): 
            rin = rgrid[i,n]
            print("i = " + str(i) + ", n = " + str(n) + ", xi = " + str(xi) + ", r = " + str(rin) )
            if rin <= params['r_cutoff']:
                for scheme in spherical_schemes[3:]: #skip 003a,003b,003c rules
                    k=0
                    for l1,m1 in sphlist:
                        for l2,m2 in sphlist:
                        
                            val[k] = calc_potmatelem_quadpy( l1, m1, l2, m2, rin, scheme, esp_interpolant )
                            print(  '%4d %4d %4d %4d'%(l1,m1,l2,m2) + '%12.6f %12.6fi' % (val[k].real, val[k].imag) + \
                                    '%12.6f %12.6fi' % (val_prev[k].real, val_prev[k].imag) + \
                                    '%12.6f %12.6fi' % (np.abs(val[k].real-val_prev[k].real), np.abs(val[k].imag-val_prev[k].imag)) + \
                                    '%12.6f '%np.abs(val[k]-val_prev[k])  )
                            k += 1

                    diff = np.abs(val - val_prev)

                    if (np.any( diff > quad_tol )):
                        print( str(scheme) + " convergence not reached" ) 
                        for k in range(len(val_prev)):
                            val_prev[k] = val[k]
                    elif ( np.all( diff < quad_tol ) ):     
                        print( str(scheme) + " convergence reached !!!")
                        sph_quad_list.append([ i, n, xi, str(scheme)])
                        xi += 1
                        break

                    #if no convergence reached raise warning
                    if ( scheme == spherical_schemes[len(spherical_schemes)-1] and np.any( diff > quad_tol )):
                        print("WARNING: convergence at tolerance level = " + str(quad_tol) + " not reached for all considered quadrature schemes")

            else:
                scheme = spherical_schemes[lmax+1]
                sph_quad_list.append([ i, n, xi, str(scheme)])
                print("r>r_cutoff: "+str(scheme))
                xi += 1


    print("Converged quadrature levels: ")
    print(sph_quad_list)
    quadfilename = params['working_dir'] + params['file_quad_levels'] 
    fl = open(quadfilename,'w')
    print("saving quadrature levels to file: " + quadfilename )
    for item in sph_quad_list:
        fl.write( str('%4d '%item[0]) + str('%4d '%item[1]) + str('%4d '%item[2]) + str(item[3]) + "\n")

    return sph_quad_list

def gen_adaptive_quads_exact(params , rgrid):

    sph_quad_list = [] #list of quadrature levels needed to achieve convergence quad_tol of the potential energy matrix elements (global)

    lmax = params['bound_lmax']
    quad_tol = params['sph_quad_tol']

    print("Adaptive quadratures generator with exact numerical potential")

    sphlist = MAPPING.GEN_SPHLIST(lmax)

    val =  np.zeros( shape = ( len(sphlist)**2 ), dtype=complex)
    val_prev = np.zeros( shape = ( len(sphlist)**2 ), dtype=complex)

    spherical_schemes = []
    for elem in list(quadpy.u3.schemes.keys()):
        if 'lebedev' in elem:
            spherical_schemes.append(elem)

    xi = 0
    for i in range(np.size( rgrid, axis=0 )): 
        for n in range(np.size( rgrid, axis=1 )): 
            rin = rgrid[i,n]
            print("i = " + str(i) + ", n = " + str(n) + ", xi = " + str(xi) + ", r = " + str(rin) )

            for scheme in spherical_schemes[3:]: #skip 003a,003b,003c rules
                k=0

                #get grid
                Gs = GRID.read_leb_quad(scheme)

                #pull potential at quadrature points
                potfilename = "esp_"+params['molec_name']+"_"+params['esp_method']+"_"+str('%6.4f'%rin)+"_"+scheme

                if os.path.isfile(params['working_dir'] + "esp/" + potfilename):
                    print (potfilename + " file exist")


                    filesize = os.path.getsize(params['working_dir'] + "esp/" + potfilename)

                    if filesize == 0:
                        print("The file is empty: " + str(filesize))
                        os.remove(params['working_dir'] + "esp/" + potfilename)
                        GRID.GEN_XYZ_GRID([Gs],np.array(rin),params['working_dir']+"esp/")

                        V = GRID.CALC_ESP_PSI4(params['working_dir']+"esp/")
                        V = np.asarray(V)

                        fl = open(params['working_dir'] + "esp/" + potfilename,"w")
                        np.savetxt(fl,V,fmt='%10.6f')

                    else:
                        print("The file is not empty: " + str(filesize))
                        fl = open(params['working_dir'] + "esp/" + potfilename , 'r' )
                        V = []
                        for line in fl:
                            words = line.split()
                            potval = -1.0 * float(words[0])
                            V.append(potval)
                        V = np.asarray(V)
    
                else:
                    print (potfilename + " file does not exist")

                    #generate xyz grid 
                    GRID.GEN_XYZ_GRID([Gs],np.array(rin),params['working_dir']+"esp/")

                    V = GRID.CALC_ESP_PSI4(params['working_dir']+"esp/")
                    V = np.asarray(V)

                    fl = open(params['working_dir'] + "esp/" + potfilename,"w")
                    np.savetxt(fl,V,fmt='%10.6f')


                for l1,m1 in sphlist:
                    for l2,m2 in sphlist:

                        val[k] = calc_potmatelem_xi( V, Gs, l1, m1, l2, m2 )

                        #val[k] = calc_potmatelem_quadpy( l1, m1, l2, m2, rin, scheme, esp_interpolant )

                        print(  '%4d %4d %4d %4d'%(l1,m1,l2,m2) + '%12.6f' % val[k] + \
                                '%12.6f' % (val_prev[k]) + \
                                '%12.6f '%np.abs(val[k]-val_prev[k])  )
                        k += 1

                diff = np.abs(val - val_prev)

                if (np.any( diff > quad_tol )):
                    print( str(scheme) + " convergence not reached" ) 
                    for k in range(len(val_prev)):
                        val_prev[k] = val[k]
                elif ( np.all( diff < quad_tol ) ):     
                    print( str(scheme) + " convergence reached !!!")
                    sph_quad_list.append([ i, n, xi, str(scheme)])
                    xi += 1
                    break

                #if no convergence reached raise warning
                if ( scheme == spherical_schemes[len(spherical_schemes)-1] and np.any( diff > quad_tol )):
                    print("WARNING: convergence at tolerance level = " + str(quad_tol) + " not reached for all considered quadrature schemes")
                    print( str(scheme) + " convergence reached !!!")
                    sph_quad_list.append([ i, n, xi, str(scheme)])
                    xi += 1

    print("Converged quadrature levels: ")
    print(sph_quad_list)
    quadfilename = params['working_dir'] + params['file_quad_levels'] 
    fl = open(quadfilename,'w')
    print("saving quadrature levels to file: " + quadfilename )
    for item in sph_quad_list:
        fl.write( str('%4d '%item[0]) + str('%4d '%item[1]) + str('%4d '%item[2]) + str(item[3]) + "\n")

    return sph_quad_list


""" ============ PLOTS ============ """
def plot_mat(mat):
    """ plot 2D array with color-coded magnitude"""
    fig, ax = plt.subplots()

    im, cbar = heatmap(mat, 0, 0, ax=ax, cmap="gnuplot", cbarlabel="Hij")

    fig.tight_layout()
    plt.show()

def heatmap( data, row_labels, col_labels, ax=None,
            cbar_kw={}, cbarlabel="", **kwargs ):
    """
    Create a heatmap from a numpy array and two lists of labels.

    Parameters
    ----------
    data
        A 2D numpy array of shape (N, M).
    row_labels
        A list or array of length N with the labels for the rows.
    col_labels
        A list or array of length M with the labels for the columns.
    ax
        A `matplotlib.axes.Axes` instance to which the heatmap is plotted.  If
        not provided, use current axes or create a new one.  Optional.
    cbar_kw
        A dictionary with arguments to `matplotlib.Figure.colorbar`.  Optional.
    cbarlabel
        The label for the colorbar.  Optional.
    **kwargs
        All other arguments are forwarded to `imshow`.
    """

    if not ax:
        ax = plt.gca()

    # Plot the heatmap
    im = ax.imshow(np.abs(data), **kwargs)

    # Create colorbar
    im.set_clim(0, np.max(np.abs(data)))
    cbar = ax.figure.colorbar(im, ax=ax,    **cbar_kw)
    cbar.ax.set_ylabel(cbarlabel, rotation=-90, va="bottom")

    # We want to show all ticks...
    ax.set_xticks(np.arange(data.shape[1]))
    ax.set_yticks(np.arange(data.shape[0]))
    # ... and label them with the respective list entries.
    """ax.set_xticklabels(col_labels)
    ax.set_yticklabels(row_labels)"""

    # Let the horizontal axes labeling appear on top.
    ax.tick_params(top=True, bottom=False,
                labeltop=True, labelbottom=False)

    # Rotate the tick labels and set their alignment.
    #plt.setp(ax.get_xticklabels(), rotation=-30, ha="right",rotation_mode="anchor")

    # Turn spines off and create white grid.
    for edge, spine in ax.spines.items():
        spine.set_visible(False)

    #ax.set_xticks(np.arange(data.shape[1]+1)-.5, minor=True)
    #ax.set_yticks(np.arange(data.shape[0]+1)-.5, minor=True)
    ax.grid(which="minor", color="w", linestyle='-', linewidth=3)
    #ax.tick_params(which="minor", bottom=False, left=False)

    return im, cbar

def plot_wf_rad(rmin,rmax,npoints,coeffs,maparray,rgrid,nlobs,nbins):
    """plot the selected wavefunctions functions"""
    """ Only radial part is plotted"""

    r = np.linspace(rmin,rmax,npoints,endpoint=True,dtype=float)

    x=np.zeros(nlobs)
    w=np.zeros(nlobs)
    x,w=GRID.gauss_lobatto(nlobs,14)
    w=np.array(w)
    x=np.array(x) # convert back to np arrays
    nprint = 2 #how many functions to print

    y = np.zeros((len(r),nprint))

    for l in range(0,nprint): #loop over eigenfunctions
        #counter = 0
        for ipoint in maparray:
            #print(ipoint)
            #print(coeffs[ipoint[4]-1,l])
            y[:,l] +=  coeffs[ipoint[2]-1,l] * chi(ipoint[0],ipoint[1],r,rgrid,w,nlobs,nbins) * SH(ipoint[3], ipoint[4], theta=np.zeros(1), phi=np.zeros(1))
                #counter += 1

    plt.xlabel('r/a.u.')
    plt.ylabel('Radial eigenfunction')
    plt.legend()   
    for n in range(1,nprint):
        plt.plot(r, np.abs(y[:,n])**2)
        
        # plt.plot(r, h_radial(r,1,0))
    plt.show()     

def chi(i,n,r,rgrid,w,nlobs,nbins):
    # r is the argument f(r)
    # rgrid is the radial grid rgrid[i][n]
    # w are the unscaled lobatto weights

    w /=sum(w[:]) #normalization!!!
    val=np.zeros(np.size(r))
    
    if n==0 and i<nbins-1: #bridge functions
        #print("bridge: ", n,i)
        val = ( f(i,nlobs-1,r,rgrid,nlobs,nbins) + f(i+1,0,r,rgrid,nlobs,nbins) ) * np.sqrt( float( w[nlobs-1] ) + float( w[0] ) )**(-1)
        #print(type(val),np.shape(val))
        return val 
    elif n>0 and n<nlobs-1:
        val = f(i,n,r,rgrid,nlobs,nbins) * np.sqrt( float( w[n] ) ) **(-1) 
        #print(type(val),np.shape(val))
        return val
    else:
        return val
         
def f(i,n,r,rgrid,nlobs,nbins): 
    """calculate f_in(r). Input r can be a scalar or a vector (for quadpy quadratures) """
    
    #print("shape of r is", np.shape(r), "and type of r is", type(r))

    if np.isscalar(r):
        prod=1.0
        if  r>= rgrid[i][0] and r <= rgrid[i][nlobs-1]:
            for mu in range(0,nbins):
                if mu !=n:
                    prod*=(r-rgrid[i][mu])/(rgrid[i][n]-rgrid[i][mu])
            return prod
        else:
            return 0.0

    else:
        prod=np.ones(np.size(r), dtype=float)
        for j in range(0,np.size(r)):

            if  r[j] >= rgrid[i,0] and r[j] <= rgrid[i,nlobs-1]:

                for mu in range(0,nbins):
                    if mu !=n:
                        prod[j] *= (r[j]-rgrid[i,mu])/(rgrid[i,n]-rgrid[i,mu])
                    else:
                        prod[j] *= 1.0
            else:
                prod[j] = 0.0
    return prod

def show_Y_lm(l, m):
    """plot the angular basis"""
    theta_1d = np.linspace(0,   np.pi,  2*91) # 
    phi_1d   = np.linspace(0, 2*np.pi, 2*181) # 

    theta_2d, phi_2d = np.meshgrid(theta_1d, phi_1d)
    xyz_2d = np.array([np.sin(theta_2d) * np.sin(phi_2d), np.sin(theta_2d) * np.cos(phi_2d), np.cos(theta_2d)]) #2D grid of cartesian coordinates

    colormap = cm.ScalarMappable( cmap=plt.get_cmap("cool") )
    colormap.set_clim(-.45, .45)
    limit = .5

    print("Y_%i_%i" % (l,m)) # zeigen, dass was passiert
    plt.figure()
    ax = plt.gca(projection = "3d")
    
    plt.title("$Y^{%i}_{%i}$" % (m,l))

    Y_lm = spharm(l,m, theta_2d, phi_2d)
    #Y_lm = self.solidharm(l,m,1,theta_2d,phi_2d)
    print(np.shape(Y_lm))
    r = np.abs(Y_lm.real)*xyz_2d #calculate a point in 3D cartesian space for each value of spherical harmonic at (theta,phi)
    
    ax.plot_surface(r[0], r[1], r[2], facecolors=colormap.to_rgba(Y_lm.real), rstride=1, cstride=1)
    ax.set_xlim(-limit,limit)
    ax.set_ylim(-limit,limit)
    ax.set_zlim(-limit,limit)
    #ax.set_aspect("equal")
    #ax.set_axis_off()
    
            
    plt.show()

def spharm(l,m,theta,phi):
    return sph_harm(m, l, phi, theta)


if __name__ == "__main__":      


    params = input.gen_input()
    BUILD_HMAT0(params)

